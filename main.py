# main.py
import os
import asyncio
from typing import NamedTuple

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import firestore_manager
import gemini_summarizer

# .envファイルから環境変数を読み込む
load_dotenv()

# キューに入れるタスクのデータ構造を定義
class ClipTask(NamedTuple):
    interaction: discord.Interaction
    message: discord.Message

# Botのクライアントを作成
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# リクエストを処理するための非同期キュー
clip_queue = asyncio.Queue()

# --- Botのイベントハンドラ ---
@client.event
async def on_ready():
    """Botが起動したときに呼び出される"""
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')
    # キュー処理タスクを開始
    process_clip_queue.start()
    # コマンドをDiscordに同期
    await tree.sync()

# --- アプリケーションコマンド（右クリックメニュー） ---
@tree.context_menu(name='clipnote')
async def clipnote(interaction: discord.Interaction, message: discord.Message):
    """メッセージを右クリックして実行されるコマンド"""
    # 5秒以内に応答しないとタイムアウトするため、先に応答メッセージを送る
    await interaction.response.send_message(
        "📎 clipnoteに登録リクエストを受け付けました。処理を開始します...", 
        ephemeral=True # ephemeral=Trueで本人にしか見えないメッセージになる
    )
    # 処理タスクをキューに追加
    task = ClipTask(interaction=interaction, message=message)
    await clip_queue.put(task)


# --- スラッシュコマンド（管理者用） ---
@tree.command(name="set_clip_channel", description="clipnoteの投稿先チャンネルを設定します（管理者のみ）")
@app_commands.describe(channel="投稿先のテキストチャンネル")
@app_commands.checks.has_permissions(administrator=True)
async def set_clip_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    """投稿先チャンネルを設定するコマンド"""
    await interaction.response.defer(ephemeral=True) # 処理に時間がかかる可能性があるのでdefer
    try:
        await firestore_manager.set_channel(interaction.guild_id, channel.id)
        await interaction.followup.send(f"✅ 投稿先チャンネルを {channel.mention} に設定しました。")
    except Exception as e:
        print(f"Error setting channel: {e}")
        await interaction.followup.send("❌ チャンネル設定中にエラーが発生しました。")

@tree.command(name="show_clip_channel", description="clipnoteの現在の投稿先チャンネルを表示します")
async def show_clip_channel(interaction: discord.Interaction):
    """現在の投稿先チャンネルを確認するコマンド"""
    await interaction.response.defer(ephemeral=True)
    channel_id = await firestore_manager.get_channel_id(interaction.guild_id)
    if channel_id:
        channel = interaction.guild.get_channel(channel_id)
        if channel:
            await interaction.followup.send(f"現在の投稿先は {channel.mention} です。")
        else:
            await interaction.followup.send("⚠️ 投稿先チャンネルが設定されていますが、見つかりませんでした。再設定してください。")
    else:
        await interaction.followup.send("ℹ️ 投稿先チャンネルはまだ設定されていません。`/set_clip_channel`で設定してください。")
        
@tree.command(name="remove_clip_channel", description="clipnoteの投稿先チャンネル設定を削除します（管理者のみ）")
@app_commands.checks.has_permissions(administrator=True)
async def remove_clip_channel(interaction: discord.Interaction):
    """投稿先チャンネル設定を削除するコマンド"""
    await interaction.response.defer(ephemeral=True)
    try:
        await firestore_manager.remove_channel(interaction.guild_id)
        await interaction.followup.send("✅ 投稿先チャンネルの設定を削除しました。")
    except Exception as e:
        print(f"Error removing channel: {e}")
        await interaction.followup.send("❌ 設定削除中にエラーが発生しました。")


# --- エラーハンドリング ---
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ このコマンドを実行するには管理者権限が必要です。", ephemeral=True)
    else:
        print(f"Unhandled command error: {error}")
        await interaction.response.send_message("❌ コマンドの実行中に予期せぬエラーが発生しました。", ephemeral=True)


# --- キュー処理のバックグラウンドタスク ---
@tasks.loop(seconds=1.0) # 1秒ごとにキューをチェック
async def process_clip_queue():
    if not clip_queue.empty():
        task: ClipTask = await clip_queue.get()
        try:
            await process_clip(task.interaction, task.message)
        except Exception as e:
            print(f"Error processing queue task for message {task.message.id}: {e}")
            await task.interaction.followup.send(
                f"❌ メッセージ({task.message.jump_url})の処理中にエラーが発生しました。",
                ephemeral=True
            )
        finally:
            clip_queue.task_done()

async def process_clip(interaction: discord.Interaction, message: discord.Message):
    """キューから取り出したタスクを実際に処理する関数"""
    guild = interaction.guild
    user = interaction.user

    # 1. 重複チェック
    if await firestore_manager.is_message_processed(message.id):
        await interaction.followup.send(f"ℹ️ このメッセージ ({message.jump_url}) は既にclipnoteに登録されています。", ephemeral=True)
        return

    # 2. 投稿先チャンネルを取得
    post_channel_id = await firestore_manager.get_channel_id(guild.id)
    if not post_channel_id:
        await interaction.followup.send("⚠️ 投稿先チャンネルが設定されていません。サーバー管理者に依頼して `/set_clip_channel` で設定してもらってください。", ephemeral=True)
        return
        
    post_channel = guild.get_channel(post_channel_id)
    if not post_channel:
        await interaction.followup.send("⚠️ 設定されている投稿先チャンネルが見つかりません。サーバー管理者に再設定を依頼してください。", ephemeral=True)
        return

    # 3. メッセージ内容を要約
    # follow-upを送信して処理中であることをユーザーに知らせる
    await interaction.followup.send(f"🤖 メッセージの要約を生成中です...", ephemeral=True)
    
    content_to_summarize = message.content
    if message.embeds:
        # 埋め込みがある場合は、その説明も要約対象に加える
        for embed in message.embeds:
            if embed.description:
                content_to_summarize += "\n" + embed.description

    summary = await gemini_summarizer.summarize_text(content_to_summarize)

    # 4. 結果をチャンネルに投稿
    embed = discord.Embed(
        # descriptionに要約とリンクを両方含める
        description=f"**要約**「{summary}」\n[元の投稿はこちら]({message.jump_url})",
        color=discord.Color.blue()
    )
    # embed.add_field(...) の行を削除！
    embed.set_author(name=f"Clipped by {user.display_name}", icon_url=user.avatar.url if user.avatar else user.default_avatar.url)
    embed.set_footer(text=f"from #{message.channel.name}")
    embed.timestamp = message.created_at

    await post_channel.send(embed=embed)

    # 5. 処理済みとしてマーク
    await firestore_manager.mark_message_as_processed(message.id, guild.id, message.jump_url)

    # 6. 完了通知
    await interaction.followup.send(f"✅ {post_channel.mention} にclipしました！", ephemeral=True)


# --- Botの実行 ---
if __name__ == "__main__":
    token = os.getenv('DISCORD_BOT_TOKEN')
    if token:
        client.run(token)
    else:
        print("エラー: DISCORD_BOT_TOKENが設定されていません。")