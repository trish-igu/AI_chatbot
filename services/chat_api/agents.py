"""
Multi-agent system for the conversational AI application.
Contains three specialized agents with distinct responsibilities.
"""

from typing import List, Dict, Any, Optional, Tuple
import re
from config import settings
import logging

logger = logging.getLogger(__name__)

try:
    import vertexai
    from vertexai.generative_models import GenerativeModel, GenerationConfig, Content, Part, HarmCategory, HarmBlockThreshold
except Exception:
    vertexai = None  # type: ignore
    GenerativeModel = None  # type: ignore
    GenerationConfig = None  # type: ignore

_vertex_model: GenerativeModel | None = None

def _truncate_text(input_text: str, max_chars: int) -> str:
    """Return the last max_chars of input_text to keep the most recent context."""
    if not input_text:
        return ""
    if len(input_text) <= max_chars:
        return input_text
    return input_text[-max_chars:]

def _clean_trailing_fragment(text: str) -> str:
    """Clean up trailing incomplete words/phrases before appending a closing sentence."""
    if not text:
        return ""
    trimmed = text.rstrip()
    # Drop dangling contractions
    contractions = ("'ve", "’ve", "'m", "’m", "'re", "’re", "'ll", "’ll", "'d", "’d")
    last = trimmed.split()[-1] if trimmed.split() else ""
    if last.endswith(contractions):
        trimmed = " ".join(trimmed.split()[:-1])
    # Drop trailing "to"
    if trimmed.lower().endswith(" to"):
        trimmed = trimmed[:-3]
    # Ensure sentence punctuation
    if not trimmed or trimmed[-1] not in ".!?":
        trimmed = trimmed.rstrip() + "."
    return trimmed

def _safe_extract_text(gen_result) -> str:
    """Extract text from a Vertex generate_content result without raising.

    Falls back to concatenating candidate content parts if result.text access
    triggers a safety/empty-candidate exception.
    """
    try:
        txt = getattr(gen_result, "text", None)
        if isinstance(txt, str):
            return txt.strip()
    except Exception:
        pass
    # Fallback: walk candidates → content.parts
    try:
        candidates = getattr(gen_result, "candidates", None) or []
        for cand in candidates:
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", None) or []
            collected = []
            for part in parts:
                # Part may expose .text or ._raw_value
                val = getattr(part, "text", None)
                if not isinstance(val, str):
                    val = getattr(part, "_raw_value", None)
                if isinstance(val, str):
                    collected.append(val)
            if collected:
                return "".join(collected).strip()
    except Exception:
        pass
    return ""

def _normalize_close(text: str) -> str:
    """Normalize and ensure greeting ends with a complete sentence.

    - Collapses ellipses/multi-dots
    - Trims dangling punctuation
    - Ensures final punctuation (adds a supportive closing if needed)
    """
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r"(\s*\.){2,}", ".", t)
    t = t.rstrip("'\" ,;:")
    if not t or t[-1] not in ".!?":
        t = (t + ". How are you feeling right now?").strip()
    return t

# NOTE: _clip_greeting intentionally removed to avoid post-generation truncation

def _build_template_greeting(name: str, topic_hint: str | None) -> str:
    """Construct a clean, warm greeting using recent phrases or summary.

    - Uses first phrase (<= 12 words) if available
    - Otherwise distills the summary to one brief topic phrase (<= 12 words)
    """
    safe_name = (name or "there").strip()
    topic = ""
    if topic_hint:
        topic = " ".join(topic_hint.strip().split()[:12]).rstrip(" .!?")

    if topic:
        return f"Hi {safe_name}, it’s really good to see you. Last time we touched on {topic}. How are things going now?"
    return f"Hi {safe_name}, it’s really good to see you. How have you been lately?"

def _ensure_vertex_initialized() -> None:
    if vertexai is None:
        raise RuntimeError("google-cloud-aiplatform (vertexai) package not available")
    vertexai.init(project=settings.vertex_project_id, location=settings.vertex_location)

def get_vertex_model() -> GenerativeModel:
    global _vertex_model
    if _vertex_model is None:
        _ensure_vertex_initialized()
        model_name = settings.vertex_model_name or "gemini-2.5-pro"
        # Relax guardrails to "block few" (only high severity) while prompts enforce HIPAA safety
        try:
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            _vertex_model = GenerativeModel(model_name, safety_settings=safety_settings)
        except Exception:
            _vertex_model = GenerativeModel(model_name)
    return _vertex_model

async def core_chat_agent(
    history: List[Dict[str, Any]],
    user_message: str,
    cumulative_context: str = None,
    suppress_greeting: bool = False,
    first_name: Optional[str] = None,
) -> Tuple[str, Dict[str, int], str]:
    """
    Core chat agent responsible for generating conversational replies with personal insights and HIPAA compliance.
    
    Args:
        history: List of previous conversation messages
        user_message: The user's current message
        cumulative_context: Context from all previous conversation summaries
        
    Returns:
        AI's conversational response
    """
    try:
        # Vertex-only
        # Prepare system prompt with HIPAA compliance, therapeutic stance, and continuity
        system_prompt = """You are Mindy, a calm, grounded, therapist‑like mental health assistant.

THERAPEUTIC STANCE (no sycophancy):
- Be an ally: validate and reflect feelings first; avoid flattery and excessive praise.
- Use collaborative language (“we can…”, “let’s try…”), not command‑and‑control.
- Ask at most ONE brief, insightful question—and only if helpful. If the user is venting, ask no question.
- Avoid interrogation: never ask multiple questions in a row; no rapid‑fire follow‑ups.
- Keep boundaries: no diagnosis. If risk is implied, gently suggest professional resources.

CONTINUITY & CONTEXT:
- If prior context is provided, reference 1–2 specific themes using the user’s own words when safe.
- Prefer recent history over older summaries when they conflict.
- If no context is provided, do not imply memory from past chats.

STYLE & LENGTH:
- 4–6 concise sentences (≤ ~180 words). Clear, skimmable, and warm.
- Avoid repetitive phrases and filler (“I’m sorry” more than once, excessive exclamations).
- Offer exactly ONE concrete coping step only if appropriate, with 1–2 sentences on how to try it now.

HIPAA SAFETY:
- Do not request or include personal identifiers.
- Focus on emotions, patterns, and coping—not private details.

TOOLKIT (choose ONE when helpful; include its bracket label so the app can surface it):
- 2‑minute Box Breathing [Breathing Exercise]
- 5‑4‑3‑2‑1 Grounding [Grounding Tool]
- Thought Reframe [CBT Thought Record]
- Quick Journal Prompt [Journaling]
- Progressive Muscle Relaxation (3 min) [PMR]
- Gratitude Check‑in [Gratitude Note]
"""

        # Consolidate all system instructions into a single message
        system_instructions = [system_prompt]
        if cumulative_context and cumulative_context != "No previous conversation history available.":
            system_instructions.append(
                f"Previous conversation context:\n{cumulative_context}\n\nUse this context to provide personalized, continuous care while maintaining HIPAA compliance."
            )
        else:
            system_instructions.append(
                "No prior conversation context is available. Do not claim to remember previous chats. Treat this as the first conversation."
            )
        if suppress_greeting:
            system_instructions.append(
                "Do not include any greeting or pleasantries. Respond directly to the user's message in 3–6 sentences. Use reflective listening, validation, and a supportive, therapist-like tone. Ask one gentle, open-ended question and, if helpful, offer 1–2 practical coping steps."
            )
        else:
            name_for_greeting = (first_name or "there").strip()
            system_instructions.append(f"Start your reply with: 'Hi {name_for_greeting},' then continue.")
        # Add repetition/finish guardrail directly into the consolidated system prompt
        system_instructions.append(
            "Avoid repeating phrases. Provide a complete response that ends with a full sentence."
        )
        final_system_prompt = "\n\n".join(system_instructions)
        messages = [{"role": "system", "content": final_system_prompt}]
        
        # Add conversation history with CRITICAL role correction (assistant -> model)
        corrected_history: List[Dict[str, Any]] = []
        for msg in history:
            role = (msg.get("role") or "").lower()
            content = msg.get("content", "")
            if role == "assistant":
                corrected_history.append({"role": "model", "content": content})
            else:
                corrected_history.append({"role": role or "user", "content": content})
        messages.extend(corrected_history)
        
        # Add the current user message
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        model = get_vertex_model()
        gen_config = GenerationConfig(
            temperature=0.7,
            max_output_tokens=1792,  # ample space for multi-sentence replies
            top_p=0.95,
            top_k=40,
            frequency_penalty=0.4,
            presence_penalty=0.1,
        )
        # Build contents with consolidated system and role mapping
        contents = []
        msgs = list(messages)
        if msgs and (msgs[0].get("role") or "").lower() == "system":
            sys = msgs.pop(0)
            contents.append(Content(role="user", parts=[Part.from_text(sys.get("content", ""))]))
            contents.append(Content(role="model", parts=[Part.from_text("")]))
        for m in msgs:
            role = (m.get("role") or "user").lower()
            text = m.get("content", "")
            if role == "assistant":
                role = "model"
            elif role == "system":
                role = "user"
            contents.append(Content(role=role, parts=[Part.from_text(text)]))
        result = model.generate_content(contents, generation_config=gen_config, stream=False)
        text = _safe_extract_text(result)
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        model_name = settings.vertex_model_name or "gemini-2.5-pro"
        # Minimal completion pass only if we clearly ended mid-sentence
        if text and text.strip() and text.strip()[-1] not in ".!?":
            finish_sys = (
                "Complete only the unfinished ending of the user's last sentence. "
                "Return just the missing ending (<= 25 words), no repetition, end with a period."
            )
            finish_msgs = [
                {"role": "system", "content": finish_sys},
                {"role": "user", "content": f"Partial: {text.strip()}\nCompletion:"},
            ]
            f_contents = []
            for m in finish_msgs:
                role = (m.get("role") or "user").lower()
                if role == "system":
                    role = "user"
                f_contents.append(Content(role=role, parts=[Part.from_text(m.get("content", ""))]))
            f_contents.append(Content(role="model", parts=[Part.from_text("")]))
            f_result = model.generate_content(
                f_contents,
                generation_config=GenerationConfig(temperature=0.6, max_output_tokens=64),
                stream=False,
            )
            tail = _safe_extract_text(f_result)
            if tail:
                text = f"{text.strip()} {tail.strip()}".strip()
        text = _normalize_close(text)
        return text, usage, model_name
        
    except Exception as e:
        logger.error(f"Error in core_chat_agent: {e}")
        
        # Handle content filter errors specifically
        if "content_filter" in str(e) or "ResponsibleAIPolicyViolation" in str(e):
            logger.warning("Content filter triggered - providing safe fallback response")
            return (
                "I understand you'd like to discuss something important. I'm here to support you with your mental health and well-being. Could you please rephrase your message in a way that focuses on your emotional state or concerns?",
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                settings.vertex_model_name or "gemini-2.5-pro",
            )
        
        return (
            "I'm sorry, I'm having trouble processing your message right now. Please try again.",
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            settings.vertex_model_name or "gemini-2.5-pro",
        )

async def summarizer_agent(conversation_history: List[Dict[str, Any]], cumulative_context: str = None) -> Tuple[str, Dict[str, int], str]:
    """
    Summarizer agent responsible for generating comprehensive conversation summaries with cumulative context.
    
    Args:
        conversation_history: Full conversation history to summarize
        cumulative_context: Context from all previous conversation summaries
        
    Returns:
        Comprehensive summary of the conversation
    """
    try:
        # Vertex-only
        # Prepare the conversation text for summarization
        conversation_text = ""
        for msg in conversation_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, dict):
                content = content.get("text", str(content))
            conversation_text += f"{role}: {content}\n"
        
        system_prompt = """You are an expert mental health conversation summarizer.

Return a brief, structured summary in EXACTLY four labeled sections and nothing else:

EMOTIONAL STATE: <1 short sentence capturing the user's overall emotional tone today>
KEY TOPICS: <1 short sentence listing the main themes discussed>
PROGRESS INDICATORS: <1 short sentence about improvements/setbacks or coping actions>
SUPPORT PROVIDED: <1 short sentence summarizing validation, strategies, or next steps offered>

Rules:
- Do not include personal identifiers; focus on patterns and feelings.
- Keep total length under 120 words.
- No extra commentary outside the four labeled lines."""

        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]
        
        # Add cumulative context if available
        if cumulative_context and cumulative_context != "No previous conversation history available.":
            messages.append({
                "role": "system",
                "content": f"Previous conversation context to consider:\n{cumulative_context}\n\nUse this context to identify patterns and continuity in the user's mental health journey."
            })
        
        messages.append({
            "role": "user",
            "content": f"Please summarize this conversation:\n\n{conversation_text}"
        })
        
        model = get_vertex_model()
        gen_config = GenerationConfig(temperature=0.3, max_output_tokens=256, top_p=0.95, top_k=40)
        contents = []
        msgs = list(messages)
        if msgs and (msgs[0].get("role") or "").lower() == "system":
            sys = msgs.pop(0)
            contents.append(Content(role="user", parts=[Part.from_text(sys.get("content", ""))]))
            contents.append(Content(role="model", parts=[Part.from_text("")]))
        for m in msgs:
            role = (m.get("role") or "user").lower()
            text = m.get("content", "")
            if role == "assistant":
                role = "model"
            contents.append(Content(role=role, parts=[Part.from_text(text)]))
        result = model.generate_content(contents, generation_config=gen_config, stream=False)
        text = (result.text or "").strip()
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        model_name = settings.vertex_model_name or "gemini-2.5-pro"

        # Finish-guard: if the greeting looks truncated, ask model to complete once
        if not text or (len(text) < 20 or text[-1:] not in ".!?"):
            follow_msgs = list(messages)
            follow_msgs.append({"role": "assistant", "content": text or ""})
            follow_msgs.append({
                "role": "user",
                "content": "Finish your last reply naturally without repeating. Add 1 short closing sentence and end with a period.",
            })
            contents2 = []
            for m in follow_msgs:
                role = (m.get("role") or "user").lower()
                txt = m.get("content", "")
                if role == "assistant":
                    role = "model"
                elif role not in ("user", "model"):
                    role = "user"
                contents2.append(Content(role=role, parts=[Part.from_text(txt)]))
            result2 = model.generate_content(contents2, generation_config=GenerationConfig(temperature=0.5, max_output_tokens=128))
            more = (getattr(result2, "text", None) or "").strip()
            if more:
                tail = text[-80:].lower()
                add = more.lstrip()
                for span in (60, 40, 20):
                    if len(add) >= span and add[:span].lower() in tail:
                        add = add[span:]
                        break
                text = (text + " " + add).strip()

        # Final safety: if still no closing punctuation, add a friendly completion
        if not text or text[-1:] not in ".!?":
            text = (text.rstrip() + " to connect with you. How are you feeling right now?").strip()

        return text, usage, model_name
        
    except Exception as e:
        logger.error(f"Error in summarizer_agent: {e}")
        return (
            "Previous conversation about general topics",
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            settings.vertex_model_name or "gemini-2.5-pro",
        )

async def personalizer_agent(
    cumulative_context: str,
    first_name: Optional[str] = None,
    recent_user_phrases: Optional[list[str]] = None,
    latest_summary: Optional[str] = None,
) -> Tuple[str, Dict[str, int], str]:
    """
    Personalizer agent responsible for generating warm, welcoming greetings with cumulative context.
    
    Args:
        cumulative_context: Context from all previous conversation summaries
        
    Returns:
        Personalized greeting message
    """
    try:
        # Vertex-only
        system_prompt = """You are Mindy, a warm and caring AI mental health assistant.

GOAL:
- Create a personalized greeting that feels seen and supported, not performative.

GUIDELINES:
- Start with the user's first name.
- Reference 1–2 specific themes from the latest conversation summary (feelings, topics, progress). Use the user’s words when safe.
- Avoid flattery and excessive positivity; strike a grounded, supportive tone.
- Ask at most ONE brief, insightful question—or none if the user seems to be venting.
- Keep it short (1–2 sentences; ≤ ~45 words). No extra pleasantries beyond the greeting.

Create the greeting that:
1. WELCOMES WARMTH: Greet the user back with genuine warmth and care
2. REFERENCES HISTORY: If prior conversation context is provided, reference specific details (feelings, situations, topics, progress). If no prior context is provided, DO NOT imply prior interactions.
3. SHOWS CONTINUITY: Only when history is available, demonstrate continuity and care about ongoing progress.
4. ASKS PROGRESS: Inquire how they're doing now in relation to what they've shared before
5. HIPAA COMPLIANCE: Focus on emotional patterns and general well-being, not personal identifiers
6. ENCOURAGING TONE: Be empathetic, supportive, and encouraging

IMPORTANT: Conversation history will be provided explicitly in the prompt when available.
- If "Previous conversation context" is provided, you may reference and build upon it.
- If it is not provided, treat this as a first-time greeting and avoid implying memory.

Make it feel personal, warm, and show genuine care for their mental health journey.
"""

        name_for_greeting = (first_name or "there").strip()
        # Limit context size to reduce safety blocks and token usage
        safe_context = _truncate_text(cumulative_context or "", 4000)
        # Provide a distilled gist of recent phrases instead of verbatim echoing
        # to avoid parroting exact user words in greetings
        gist_from_phrases = ""
        if recent_user_phrases:
            # Take the most recent phrase, trim, and convert to a neutral noun-phrase
            candidate = (recent_user_phrases[0] or "").strip()
            if candidate:
                gist_from_phrases = " ".join(candidate.split()[:10]).rstrip(" .!?")
        phrases_hint = (f"\n\nGIST FROM RECENT MESSAGES (one neutral phrase; paraphrase; no quotes): {gist_from_phrases}"
                        if gist_from_phrases else "")

        # Prefer the latest summary for personalization; fall back to cumulative context
        # If no real summary exists, avoid dropping generic placeholders into the prompt
        last_summary_text = (latest_summary or "").strip()
        if last_summary_text and last_summary_text.lower() != "previous conversation about general topics":
            last_summary_block = (
                f"\n\nLATEST CONVERSATION SUMMARY (use 1–2 key topics/feelings from this, paraphrased):\n{_truncate_text(last_summary_text, 800)}"
            )
            topic_hint = last_summary_text
        else:
            last_summary_block = ""
            topic_hint = gist_from_phrases

        messages = [
            {
                "role": "system",
                "content": system_prompt + last_summary_block + phrases_hint
            },
            {
                "role": "user",
                "content": f"Generate a warm, personalized greeting that begins with 'Hi {name_for_greeting},' for a user with this conversation history:\n\n{safe_context}"
            }
        ]
        
        model = get_vertex_model()
        gen_config = GenerationConfig(temperature=0.8, max_output_tokens=1024, top_p=0.95, top_k=40)
        contents = []
        msgs = list(messages)
        if msgs and (msgs[0].get("role") or "").lower() == "system":
            sys = msgs.pop(0)
            contents.append(Content(role="user", parts=[Part.from_text(sys.get("content", ""))]))
            contents.append(Content(role="model", parts=[Part.from_text("")]))
        for m in msgs:
            role = (m.get("role") or "user").lower()
            text = m.get("content", "")
            if role == "assistant":
                role = "model"
            contents.append(Content(role=role, parts=[Part.from_text(text)]))
        result = model.generate_content(contents, generation_config=gen_config, stream=False)
        text = _safe_extract_text(result)
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        model_name = settings.vertex_model_name or "gemini-2.5-pro"
        if not text:
            text = f"Hi {name_for_greeting}, it’s good to see you again. How have you been?"
        # Only ensure well-formed punctuation; avoid truncating a good response
        text = _normalize_close(text)
        return text, usage, model_name
        
    except Exception as e:
        logger.error(f"Error in personalizer_agent: {e}")
        # Neutral, no-memory fallback to avoid false claims
        return (
            "Hi, I’m here for you. How can I support your well-being today?",
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            settings.vertex_model_name or "gemini-2.5-pro",
        )


