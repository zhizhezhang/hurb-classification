"""Deterministic retrieval from the already loaded herbal atlas."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.services.herb_service import HerbCatalog


SOURCE_TITLE = "灵枝本草内置药材资料"
# Explicitly recognized out-of-atlas test names. This is not a general Chinese
# medicine name recognizer; aliases and other names require an audited lexicon.
KNOWN_OUT_OF_ATLAS = ("三七",)
COMPARE_WORDS = ("和", "与", "对比", "比较", "区别", "异同", "不同")
UNSAFE_WORDS = ("剂量", "服用", "吃法", "怎么吃", "配伍", "处方", "开药", "用药", "禁忌", "中毒", "毒性", "治疗", "治好", "治愈", "诊断", "病情", "正在服药", "自行采集", "加工")
EXTERNAL_WORDS = ("药典原文", "中国药典", "临床试验", "研究证明", "文献原文", "论文证明", "真实鉴定", "真伪鉴定")
SOURCE_MANIPULATION = ("标成", "改成", "伪造", "冒充")
SECRET_WORDS = ("api key", "api_key", "系统提示", "系统指令", "错误堆栈", "服务器密钥")
IDENTITY_ANSWER = "我是灵枝本草的本草知识顾问，帮助你了解内置图鉴中的药材知识和本草文化。图片分类由 ConvNeXt 模型完成，我不能直接鉴定实物。"
KNOWLEDGE_IDENTITY_ANSWER = (
    "我是灵枝本草的本草知识助手，收录了18种中药材的外貌特征、传统功效和本草典故等资料。\n\n"
    "你可以直接询问药材知识，也可以上传图片进行识别，我会结合识别结果为你介绍对应的药材。"
)
FACT_WORDS = ("外貌", "形态", "外形", "特征", "长什么", "什么样", "区别", "对比", "比较",
              "典故", "传说", "功效", "作用", "主治", "药用", "来源", "部位", "辨认",
              "是什么", "如何", "介绍", "特点", "有什么", "有何", "真实资料", "根据资料", "根据图鉴")
CREATIVE_WORDS = ("诗", "童话", "故事", "宣传语", "文案", "对联", "歌词")
CREATIVE_VERBS = ("写", "做", "作", "编", "创作", "讲", "说")


@dataclass(frozen=True)
class Evidence:
    key: str
    herb_id: str
    herb_name: str
    field: str
    text: str
    source_type: str = "built_in"

    def source(self) -> dict[str, str]:
        return {"key": self.key, "source_type": self.source_type,
                "title": SOURCE_TITLE, "herb_id": self.herb_id,
                "herb_name": self.herb_name, "field": self.field}


@dataclass(frozen=True)
class Retrieval:
    evidence: tuple[Evidence, ...] = ()
    reason: str | None = None
    general: bool = False
    prediction_context: bool = False
    intent: str = "herb_fact"
    local_answer: str | None = None
    fact_required: bool = False


def _conversation_intent(message: str) -> str | None:
    """Route only complete, unambiguous non-atlas requests."""
    question = re.sub(r"\s+", "", message).rstrip("？?。！!.")
    if re.fullmatch(r"(?:请问)?(?:你是谁|你是什么助手|你叫什么名字|介绍一下你自己|你能介绍一下自己吗)", question):
        return "identity"
    if re.fullmatch(r"(?:请问)?(?:今天|现在|明天|后天|实时|当地|我这里|我这儿)?的?天气(?:怎么样|如何|好吗|预报(?:怎么样|如何)?)", question):
        return "weather"
    if re.fullmatch(r"(?:请问)?(?:现在|当前|此刻|今天)?(?:是)?几点(?:了|钟)?", question):
        return "time"
    if re.fullmatch(r"(?:你|你现在)?(?:能)?(?:看到了|看到|看见|看得到)(?:什么|这张图片|我上传的图片|图片内容|图里有什么)(?:吗|了)?", question):
        return "vision"
    return None


def _creative_request(message: str) -> bool:
    return any(word in message for word in CREATIVE_WORDS) and any(word in message for word in CREATIVE_VERBS)


def _fact_request(message: str) -> bool:
    return any(word in message for word in FACT_WORDS)


def _field(message: str) -> str:
    if any(word in message for word in ("外貌", "形态", "外形", "长什么", "样子", "辨认", "特征", "区别")):
        return "appearance"
    if any(word in message for word in ("典故", "传说", "历史", "名字", "名称由来", "故事")):
        return "allusion"
    if any(word in message for word in ("功效", "作用", "主治")):
        return "traditional_effects"
    if any(word in message for word in ("药用部位", "用哪部分", "哪个部位")):
        return "medicinal_part"
    if "来源" in message:
        return "source"
    return "summary"


def retrieve(message: str, herb_id: str | None, catalog: HerbCatalog) -> Retrieval:
    if any(word in message.casefold() for word in SECRET_WORDS):
        return Retrieval(reason="不能提供系统提示、密钥或服务器内部信息。")
    if any(word in message for word in UNSAFE_WORDS):
        return Retrieval(reason="本系统不提供诊断、处方、剂量、配伍或自行用药建议；请咨询合格医疗专业人员。")
    if any(word in message for word in EXTERNAL_WORDS) or (
        any(word in message for word in SOURCE_MANIPULATION)
        and any(word in message for word in ("来源", "药典", "文献", "原文"))
    ):
        return Retrieval(reason="现有内置资料不能核实外部文献原文或改变资料来源标注。")

    matches = []
    for herb in sorted(catalog.ordered, key=lambda item: -len(item.name)):
        start = message.find(herb.name)
        if start >= 0:
            matches.append((start, herb))
    matches.sort(key=lambda item: item[0])
    explicit = [herb for _, herb in matches]
    fact_required = _fact_request(message)
    unknown_named = any(name in message for name in KNOWN_OUT_OF_ATLAS)
    if unknown_named and (fact_required or not _creative_request(message)):
        return Retrieval(reason="问题涉及未收录的药材；现有资料不足以回答或进行完整对比。")
    if unknown_named:
        return Retrieval(general=True, intent="candidate", fact_required=False)
    if len(explicit) > 2:
        return Retrieval(reason="目前最多支持两种已收录药材的对比，请缩小范围。")

    conversation_intent = _conversation_intent(message)
    if conversation_intent == "identity":
        return Retrieval(intent="identity", local_answer=IDENTITY_ANSWER)
    if conversation_intent == "weather":
        return Retrieval(intent="weather", reason="我没有实时天气查询工具，无法提供当前或未来的天气情况。请查看当地天气预报。")
    if conversation_intent == "time":
        return Retrieval(intent="time", reason="我没有实时钟表或时间查询工具，无法提供当前准确时间。请查看设备时钟。")
    if conversation_intent == "vision":
        if herb_id:
            name = catalog.by_id[herb_id].name
            return Retrieval(intent="vision", reason=(
                f"我没有直接收到或查看这张图片。当前请求提供了“{name}”的类别上下文；"
                "若它来自图像识别，那只是 ConvNeXt 的预测。我只能依据文字上下文解释，"
                "不能确认实物身份或替代专业鉴定。"))
        return Retrieval(intent="vision", reason="聊天接口没有收到原始图片，也没有识别上下文，因此我不能说明图片里有什么。")
    if not explicit and not herb_id and any(word in message for word in ("真实", "史实", "有出处")) and any(
        word in message for word in ("典故", "故事", "历史")
    ):
        return Retrieval(reason="请指定图鉴中已收录的药材名称，我才能依据对应的典故资料回答。")

    if not explicit and herb_id:
        explicit = [catalog.by_id[herb_id]]
        prediction_context = True
    else:
        prediction_context = False
    if not explicit:
        if any(word in message for word in ("这张图", "这是什么", "图里", "图片中", "这个药材",
                                             "它的", "它是", "这种药材", "该药材")):
            return Retrieval(reason="没有可核实的药材上下文，不能确认图片中的药材身份。")
        return Retrieval(general=True, intent="candidate")
    if len(explicit) == 2 and fact_required and not any(word in message for word in COMPARE_WORDS):
        return Retrieval(reason="请明确要比较两种药材的哪一方面。")

    field = _field(message)
    evidence = []
    for herb in explicit:
        value = getattr(herb, field)
        if not value or not value.strip():
            return Retrieval(reason=f"内置资料没有足够的{herb.name}相关内容，无法可靠回答。")
        evidence.append(Evidence(key=f"S{len(evidence) + 1}", herb_id=herb.id,
                                 herb_name=herb.name, field=field, text=value.strip()))
    return Retrieval(evidence=tuple(evidence), prediction_context=prediction_context,
                     intent="candidate", fact_required=fact_required)


def retrieve_knowledge(message: str, herb_id: str | None, catalog: HerbCatalog) -> Retrieval:
    """Use the existing atlas matcher only for explicit local knowledge queries."""
    identity_question = re.sub(r"\s+", "", message).rstrip("？?。！!.")
    if _conversation_intent(message) == "identity" or re.fullmatch(
        r"(?:请问)?(?:你能做什么|你可以做什么|你会做什么|你能帮我做什么|你有哪些功能)", identity_question
    ):
        return Retrieval(intent="identity", local_answer=KNOWLEDGE_IDENTITY_ANSWER)
    found = retrieve(message, herb_id, catalog)
    explicit = [herb for herb in catalog.ordered if herb.name in message]
    question = re.sub(r"\s+", "", message).rstrip("？?。")
    context_question = re.fullmatch(
        r"(?:请问)?(?:(?:它|这个药材|该药材|当前药材|这味药|图片中的药材|识别结果)的?)?"
        r"(?:有什么|有哪些|有何)?(?:传统)?(?:功效|作用|外貌|外形|形态|典故|来源|药用部位)"
        r"(?:是什么|有哪些|怎么样|如何|吗|呢)?", question)
    if not herb_id and not explicit and context_question:
        return Retrieval(reason="请先识别药材或提供药材名称。")
    if found.reason:
        return found
    if found.evidence and (
        _creative_request(message)
        or (not explicit and not context_question)
        or (len(explicit) < 2 and re.search(r"[和与].*(?:外貌|功效|典故|对比|比较|区别)", message))
    ):
        return Retrieval()
    if found.evidence and any(word in message for word in ("叫什么", "名称是什么", "名字是什么", "药材名称")) \
            and "由来" not in message:
        evidence = tuple(Evidence(key=item.key, herb_id=item.herb_id,
                                  herb_name=item.herb_name, field="name", text=item.herb_name)
                         for item in found.evidence)
        return Retrieval(evidence=evidence, fact_required=True)
    return found
