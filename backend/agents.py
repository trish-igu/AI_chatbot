"""
Multi-agent system for the conversational AI application.
Contains three specialized agents with distinct responsibilities.
"""

from typing import List, Dict, Any, Optional, Tuple
from config import settings
import logging

logger = logging.getLogger(__name__)

# Vertex AI SDK
try:
	import vertexai
	from vertexai.generative_models import GenerativeModel, GenerationConfig, Content, Part
except Exception:
	vertexai = None  # type: ignore
	GenerativeModel = None  # type: ignore
	GenerationConfig = None  # type: ignore

_vertex_model: Optional[GenerativeModel] = None


def _ensure_vertex_initialized() -> None:
	if vertexai is None:
		raise RuntimeError("google-cloud-aiplatform (vertexai) package not available")
	# Only initialize once; vertexai.init is idempotent but avoid repeated logs
	vertexai.init(project=settings.vertex_project_id, location=settings.vertex_location)


def get_vertex_model() -> GenerativeModel:
	global _vertex_model
	if _vertex_model is None:
		_ensure_vertex_initialized()
		model_name = settings.vertex_model_name or "gemini-2.5-pro"
		_vertex_model = GenerativeModel(model_name)
	return _vertex_model


def _to_vertex_contents(messages: List[Dict[str, Any]]) -> List[Content]:
	"""Convert list of {role, content} into Vertex AI Content objects.

	- Consolidate the first system message as a user message followed by a blank model
	  to seed the conversation turns.
	- Map 'assistant' -> 'model'. Preserve 'user' and 'model' roles as-is.
	"""
	contents: List[Content] = []
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
			# Convert any stray system role to user to satisfy API
			role = "user"
		contents.append(Content(role=role, parts=[Part.from_text(text)]))
	return contents


def _merge_without_repeat(existing: str, addition: str) -> str:
	"""Merge two text fragments while trimming obvious leading repetition in `addition`.

	Looks at the last ~120 chars of the existing text and removes any overlapping
	prefix (20–80 chars) from the addition before concatenation.
	"""
	if not addition:
		return existing
	add = addition.lstrip()
	tail = existing[-120:].lower()
	for span in (80, 60, 40, 20):
		if len(add) >= span and add[:span].lower() in tail:
			# Trim the overlapping prefix
			prefix = add[:span]
			pos = tail.rfind(prefix.lower())
			if pos != -1:
				add = add[span:]
				break
	combined = (existing + " " + add).strip()
	return combined


def _vertex_chat(messages: List[Dict[str, Any]], temperature: float, max_tokens: int) -> Tuple[str, Dict[str, int], str]:
	model = get_vertex_model()
	gen_config = GenerationConfig(
		temperature=temperature,
		max_output_tokens=max_tokens,
		top_p=0.9,
		top_k=40,
		frequency_penalty=0.6,
		presence_penalty=0.1,
	)
	contents = _to_vertex_contents(messages)
	result = model.generate_content(contents, generation_config=gen_config)
	text = (getattr(result, "text", None) or "").strip()
	usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
	return text, usage, settings.vertex_model_name or "gemini-2.5-pro"


async def core_chat_agent(
	history: List[Dict[str, Any]],
	user_message: str,
	cumulative_context: str = None,
	suppress_greeting: bool = False,
	first_name: Optional[str] = None,
) -> Tuple[str, Dict[str, int], str]:
	try:
		system_prompt = """You are Mindy, a warm and empathetic AI mental health assistant. Your role is to:

1. PERSONAL GREETING: Greet the user personally and warmly.
   - If prior conversation context is provided, show continuity and that you remember their journey.
   - If no prior context is provided, DO NOT claim to remember past chats; treat this as a first conversation.
2. SUPPORTIVE OBSERVATIONS: Provide gentle, supportive observations about patterns you notice in their emotional state and progress (only when grounded in provided context).
3. HIPAA COMPLIANCE: Never store, log, or reference specific personal identifiers. Focus on emotional patterns and general well-being trends.
4. SUPPORTIVE RESPONSES: Offer practical, evidence-based advice for mental health and happiness.
5. CONTINUITY: When prior context is available, reference it to show continuity of care and understanding.
6. CONTEXT AWARENESS: When history is available, use key events and relevant factors to provide personalized care. Pay close attention to the timestamps provided with each message (e.g., [YYYY-MM-DD HH:MM]) to understand the timeline of events. Prioritize the most recent messages for questions about recent events (e.g., 'yesterday').

MEMORY USAGE:
- The 'history' contains the immediate, ongoing conversation. Use it for high-fidelity, short-term recall.
- The 'Previous conversation context' is a summary of past conversations. Use it to understand long-term patterns, themes, and the user's overall journey.
- If there's a conflict between the immediate history and the long-term context, give more weight to the immediate history for recent events.

STYLE AND LENGTH:
- Be clear and easy to skim.
- Aim for 4–6 concise sentences (up to ~220 words) with a therapist-like tone.
- Use reflective listening and validation first.
- Ask AT MOST one short, gentle question; skip the question entirely if the user is venting.
- Offer exactly ONE concrete coping step from the Toolkit (below) that fits the user's state, with 1–2 sentences of how to do it right now.
- Avoid rapid‑fire questioning; focus on support and one clear next step.

IMPORTANT HIPAA GUIDELINES:
- Never ask for or reference specific personal information (names, addresses, SSNs, etc.).
- Focus on emotional and mental health patterns, not personal details.
- Maintain therapeutic boundaries while being warm and supportive.
- If you notice concerning patterns, gently suggest professional help without diagnosing.

CONTEXT USAGE:
- You will receive a system message titled "Previous conversation context" when history is available.
- If and only if that context is provided, reference relevant details from it to personalize your response.
- If no such context is provided, do not imply memory or prior interactions.

Be warm, encouraging, and show genuine care for their well-being while maintaining appropriate professional boundaries.

TOOLKIT (choose ONE when appropriate; include its bracket label so the app can surface it):
- 2-minute Box Breathing [Breathing Exercise]: Inhale 4, hold 4, exhale 4, hold 4 (repeat 4 cycles).
- 5-4-3-2-1 Grounding [Grounding Tool]: 5 things you see, 4 feel, 3 hear, 2 smell, 1 taste.
- Thought Reframe [CBT Thought Record]: Write the thought; evidence for/against; balanced alternative.
- Quick Journal Prompt [Journaling]: “Right now I need…”, “One small thing that would help is…”.
- Progressive Muscle Relaxation (3 min) [PMR]: Tense then relax muscle groups from toes to head.
- Gratitude Check-in [Gratitude Note]: Note 1–2 small things that went okay today.
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
		# Correct roles in history: assistant -> model for Vertex AI
		corrected_history: List[Dict[str, Any]] = []
		for msg in history:
			role = (msg.get("role") or "").lower()
			content = msg.get("content", "")
			if role == "assistant":
				corrected_history.append({"role": "model", "content": content})
			else:
				corrected_history.append({"role": role or "user", "content": content})
		messages.extend(corrected_history)
		messages.append({"role": "user", "content": user_message})

		text, usage, model_name = _vertex_chat(messages, temperature=0.6, max_tokens=1536)
		# If the model response looks truncated, request a short continuation once
		if not text or (len(text) < 80 or text[-1:] not in ".!?"):
			follow_msgs = list(messages)
			follow_msgs.append({"role": "assistant", "content": text or ""})
			follow_msgs.append({
				"role": "user",
				"content": "Continue your last reply without repeating any earlier phrases. Provide the final 1–2 sentences to complete the thought, and end decisively with a period."
			})
			follow_up_text, _, _ = _vertex_chat(follow_msgs, temperature=0.4, max_tokens=512)
			if follow_up_text:
				text = _merge_without_repeat(text, follow_up_text)
		return text, usage, model_name
	except Exception as e:
		logger.error(f"Error in core_chat_agent: {e}")
		return (
			"I'm sorry, I'm having trouble processing your message right now. Please try again.",
			{"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
			settings.vertex_model_name or "gemini-2.5-pro",
		)


async def summarizer_agent(conversation_history: List[Dict[str, Any]], cumulative_context: str = None) -> Tuple[str, Dict[str, int], str]:
	try:
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

		messages = [{"role": "system", "content": system_prompt}]
		if cumulative_context and cumulative_context != "No previous conversation history available.":
			messages.append({
				"role": "system",
				"content": f"Previous conversation context to consider:\n{cumulative_context}\n\nUse this context to identify patterns and continuity in the user's mental health journey."
			})
		messages.append({"role": "user", "content": f"Please summarize this conversation:\n\n{conversation_text}"})

		text, usage, model_name = _vertex_chat(messages, temperature=0.3, max_tokens=256)
		return text, usage, model_name
	except Exception as e:
		logger.error(f"Error in summarizer_agent: {e}")
		return (
			"Previous conversation about general topics",
			{"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
			settings.vertex_model_name or "gemini-2.5-pro",
		)


async def personalizer_agent(cumulative_context: str, first_name: Optional[str] = None) -> Tuple[str, Dict[str, int], str]:
	try:
		system_prompt = """You are Mindy, a warm and caring AI mental health assistant. Create a personalized greeting that:

1. WELCOMES WARMTH: Greet the user back with genuine warmth and care
2. REFERENCES HISTORY: If prior conversation context is provided, reference specific details. If no prior context is provided, DO NOT imply prior interactions.
3. SHOWS CONTINUITY: When history is available, demonstrate continuity and care about ongoing progress.
4. ASKS PROGRESS: Inquire how they're doing now in relation to what they've shared before
5. HIPAA COMPLIANCE: Focus on emotional patterns and general well-being, not personal identifiers
6. ENCOURAGING TONE: Be empathetic, supportive, and encouraging

STYLE AND LENGTH:
- Keep it brief and pleasant: 1–2 short sentences (up to ~45 words).
- Start with the user's first name if provided.
- Do not add extra pleasantries beyond the greeting."""

		name_for_greeting = (first_name or "there").strip()
		messages = [
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": f"Generate a warm, personalized greeting that begins with 'Hi {name_for_greeting},' for a user with this conversation history:\n\n{cumulative_context}"},
		]

		text, usage, model_name = _vertex_chat(messages, temperature=0.8, max_tokens=256)
		# Ensure a complete, user-friendly greeting even if the model returns something too short
		if not text or len(text.split()) < 6 or text[-1:] not in ".!?":
			name_for_greeting = (first_name or "there").strip()
			text = f"Hi {name_for_greeting}, it's good to see you. How are you feeling today?"
		return text, usage, model_name
	except Exception as e:
		logger.error(f"Error in personalizer_agent: {e}")
		return (
			"Hi, I’m here for you. How can I support your well-being today?",
			{"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
			settings.vertex_model_name or "gemini-2.5-pro",
		)
