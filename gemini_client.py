# ============================================================
# TRINITY - gemini_client.py
# Gemini API 單例管理：整個系統只初始化一次
# ============================================================

import config

_model = None


def get_model():
    """
    回傳共用的 GenerativeModel 實例。
    第一次呼叫時初始化，之後直接回傳快取實例。
    """
    global _model
    if _model is None:
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        _model = genai.GenerativeModel(config.GEMINI_MODEL)
    return _model


def is_available() -> bool:
    """確認 API Key 是否已設定"""
    return config.GEMINI_API_KEY not in ("待填入", "", None)
