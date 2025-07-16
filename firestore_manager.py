# firestore_manager.py
import os
from google.cloud import firestore

# credentials.jsonを使用して認証
# 環境変数 GOOGLE_APPLICATION_CREDENTIALS を設定する方がより安全ですが、
# 今回は簡単のため直接パスを指定します。
db = firestore.AsyncClient.from_service_account_json(
    'credentials.json',
    project=os.getenv('GCP_PROJECT_ID')
)

GUILDS_COLLECTION = 'guilds'
PROCESSED_MESSAGES_COLLECTION = 'processed_messages'

async def set_channel(guild_id: int, channel_id: int):
    """サーバーの投稿先チャンネルIDを設定/更新する"""
    guild_ref = db.collection(GUILDS_COLLECTION).document(str(guild_id))
    await guild_ref.set({'post_channel_id': channel_id})

async def get_channel_id(guild_id: int) -> int | None:
    """サーバーの投稿先チャンネルIDを取得する"""
    guild_ref = db.collection(GUILDS_COLLECTION).document(str(guild_id))
    doc = await guild_ref.get()
    if doc.exists:
        return doc.to_dict().get('post_channel_id')
    return None

async def remove_channel(guild_id: int):
    """サーバーの設定を削除する"""
    guild_ref = db.collection(GUILDS_COLLECTION).document(str(guild_id))
    await guild_ref.delete()

async def is_message_processed(message_id: int) -> bool:
    """メッセージが既に処理済みかチェックする"""
    doc_ref = db.collection(PROCESSED_MESSAGES_COLLECTION).document(str(message_id))
    doc = await doc_ref.get()
    return doc.exists

async def mark_message_as_processed(message_id: int, guild_id: int, original_message_link: str):
    """メッセージを処理済みとしてマークする"""
    doc_ref = db.collection(PROCESSED_MESSAGES_COLLECTION).document(str(message_id))
    await doc_ref.set({
        'guild_id': guild_id,
        'original_message_link': original_message_link,
        'processed_at': firestore.SERVER_TIMESTAMP
    })