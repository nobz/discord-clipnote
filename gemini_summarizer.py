# gemini_summarizer.py
import os
import google.generativeai as genai

# APIキーの設定
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# モデルの設定
generation_config = {
    "temperature": 0.7,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash-latest", # より高速なflashモデルを使用
    generation_config=generation_config,
    safety_settings=safety_settings
)

async def summarize_text(text: str) -> str:
    """与えられたテキストを2行程度に要約する"""
    if not text:
        return "（要約対象のテキストがありません）"

    prompt_parts = [
        f"以下のDiscordの投稿を、投稿者の意図を汲み取りつつ、2行程度の日本語で簡潔に要約してください。\n\n---\n{text}\n---\n\n要約:",
    ]

    try:
        response = await model.generate_content_async(prompt_parts)
        summary = response.text.strip()
        # 念のため長すぎる場合は切り詰める
        summary_lines = summary.split('\n')
        if len(summary_lines) > 3:
            return '\n'.join(summary_lines[:2]) + '...'
        return summary
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return "（要約の生成中にエラーが発生しました）"