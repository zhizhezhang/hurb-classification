"""One-turn AI knowledge questions; the other APIs do not depend on DeepSeek."""

from fastapi import APIRouter, HTTPException, Request

from backend.core.config import AISettings
from backend.schemas.ai import ChatData, ChatRequest, ChatResponse
from backend.services.ai_service import (AIServiceError, ask_deepseek, ask_deepseek_plain,
                                         direct_mode_guardrail,
                                         safe_unreferenced_content, validate_grounded_answer)
from backend.services.herb_service import HerbCatalog
from backend.services.knowledge_retrieval import KNOWN_OUT_OF_ATLAS, retrieve, retrieve_knowledge


router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    catalog: HerbCatalog | None = getattr(request.app.state, "herb_catalog", None)
    skill: str | None = getattr(request.app.state, "herbal_skill", None)
    if catalog is None or skill is None:
        raise HTTPException(status_code=503, detail="Herbal advisor is not ready")
    if body.herb_id is not None:
        if body.herb_id not in catalog.by_id:
            raise HTTPException(status_code=404, detail="Herb not found")
    settings = AISettings.from_env()
    if body.mode == "knowledge":
        found = retrieve_knowledge(body.message, body.herb_id, catalog)
        if found.local_answer:
            return ChatResponse(data=ChatData(answer=found.local_answer, herb_id=body.herb_id,
                model="local_knowledge", grounding_status="ungrounded_legacy",
                answer_origin="local_guardrail"))
        if found.evidence:
            lines = []
            for item in found.evidence:
                prefix = "根据传统本草记载，" if item.field == "traditional_effects" else ""
                lines.append(f"{prefix}{item.herb_name}：{item.text} [{item.key}]")
            return ChatResponse(data=ChatData(answer="\n".join(lines), herb_id=body.herb_id,
                model="local_knowledge", grounding_status="grounded",
                answer_origin="local_knowledge",
                sources=[item.source() for item in found.evidence]))
        guarded = found.reason and any(found.reason.startswith(prefix) for prefix in (
            "不能提供系统提示", "本系统不提供诊断", "现有内置资料不能核实外部文献",
            "请先识别药材或提供药材名称"))
        answer = found.reason if guarded else "本草知识库暂无相关内容。可切换到DeepSeek AI继续提问。"
        return ChatResponse(data=ChatData(answer=answer, herb_id=body.herb_id,
            model="local_knowledge", grounding_status="insufficient", answer_origin="local_guardrail",
            switch_recommended=not guarded))
    if body.mode == "deepseek":
        guardrail = direct_mode_guardrail(body.message)
        if guardrail:
            return ChatResponse(data=ChatData(answer=guardrail, herb_id=body.herb_id,
                model=settings.model, grounding_status="insufficient", answer_origin="local_guardrail"))
        try:
            predicted_name = catalog.by_id[body.herb_id].name if body.herb_id else None
            answer = await ask_deepseek_plain(skill, body.message, settings, predicted_name)
        except AIServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        return ChatResponse(data=ChatData(answer=answer, herb_id=body.herb_id,
            model=settings.model, grounding_status="ungrounded_legacy", answer_origin="model_general"))
    found = retrieve(body.message, body.herb_id, catalog)
    if found.reason:
        return ChatResponse(data=ChatData(answer=found.reason, herb_id=body.herb_id,
            model=settings.model, grounding_status="insufficient", answer_origin="local_guardrail"))
    if found.local_answer:
        return ChatResponse(data=ChatData(answer=found.local_answer, herb_id=body.herb_id,
            model=settings.model, grounding_status="ungrounded_legacy", answer_origin="local_guardrail"))
    try:
        generated = await ask_deepseek(skill, body.message, found.evidence, settings)
    except AIServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    def insufficient(message: str = "模型回答无法由本次图鉴证据可靠核对，请换一种问法。") -> ChatResponse:
        return ChatResponse(data=ChatData(answer=message,
            herb_id=body.herb_id, model=settings.model,
            grounding_status="insufficient", answer_origin="local_guardrail"))

    if generated.intent == "knowledge":
        if not found.fact_required or not found.evidence:
            return insufficient()
        available = {item.key for item in found.evidence}
        if set(generated.citations) != available:
            return insufficient()
        valid, used = validate_grounded_answer(generated.answer, found.evidence)
        if not valid or set(generated.citations) != {item.key for item in used}:
            return insufficient()
        answer = generated.answer
        if found.prediction_context:
            answer += "\n图片分类结果仅供学习参考，不能确认实物身份。"
        if any(item.field == "traditional_effects" for item in used):
            answer += "\n以上属于传统本草记载，不代表现代医学已证实的疗效。"
        return ChatResponse(data=ChatData(answer=answer, herb_id=body.herb_id,
            model=settings.model, grounding_status="grounded",
            answer_origin="model_with_retrieved_context",
            sources=[item.source() for item in used]))

    if found.fact_required:
        return insufficient()
    content = generated.creative_content if generated.intent == "creative" else generated.answer
    if not safe_unreferenced_content(content, tuple(item.name for item in catalog.ordered) + KNOWN_OUT_OF_ATLAS):
        return insufficient("模型回答包含无法核实的来源、药材事实或不适宜内容，请换一种问法。")
    if generated.intent == "creative" and "故事" in body.message and "虚构" not in content:
        content = "以下为原创虚构故事，并非真实历史或文献记载：\n" + content
    return ChatResponse(data=ChatData(answer=content, herb_id=body.herb_id,
        model=settings.model, grounding_status="ungrounded_legacy", answer_origin="model_general"))
