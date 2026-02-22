import json
import random
import re
from urllib import error, request

from django.conf import settings


def _clamp(value, min_value=0, max_value=100):
    return max(min_value, min(max_value, value))


def _safe_text(value, max_len=4000):
    return str(value or "").strip()[:max_len]


def _slug_key(value):
    return re.sub(r"[^a-z0-9]+", "-", _safe_text(value, 120).lower()).strip("-")


class ModuleLearningAIService:
    def __init__(self):
        self.api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
        self.model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")

    @property
    def is_ai_configured(self):
        return bool(self.api_key)

    def generate_topics(self, *, module_title, roadmap_title="", existing_topics=None, note_excerpts=None, count=10):
        count = _clamp(int(count or 10), 3, 20)
        existing_topics = self._normalize_topic_titles(existing_topics or [])
        note_excerpts = self._normalize_note_excerpts(note_excerpts or [])

        if self.is_ai_configured:
            try:
                topics = self._generate_topics_with_gemini(
                    module_title=module_title,
                    roadmap_title=roadmap_title,
                    existing_topics=existing_topics,
                    note_excerpts=note_excerpts,
                    count=count,
                )
                return {
                    "topics": topics,
                    "source": "gemini",
                    "model": self.model,
                    "note": "",
                }
            except Exception as exc:  # broad fallback by design
                fallback_topics = self._fallback_topics(
                    module_title=module_title,
                    existing_topics=existing_topics,
                    note_excerpts=note_excerpts,
                    count=count,
                )
                return {
                    "topics": fallback_topics,
                    "source": "fallback",
                    "model": "",
                    "note": f"Gemini unavailable, fallback used: {exc}",
                }

        return {
            "topics": self._fallback_topics(
                module_title=module_title,
                existing_topics=existing_topics,
                note_excerpts=note_excerpts,
                count=count,
            ),
            "source": "fallback",
            "model": "",
            "note": "",
        }

    def generate_quiz(
        self,
        *,
        module_title,
        roadmap_title="",
        quiz_mode="practice",
        topics=None,
        note_excerpts=None,
        mistakes=None,
        question_count=8,
    ):
        topics = self._normalize_topic_titles(topics or [])
        note_excerpts = self._normalize_note_excerpts(note_excerpts or [])
        mistakes = self._normalize_mistakes(mistakes or [])
        question_count = _clamp(int(question_count or 8), 4, 20)

        if self.is_ai_configured:
            try:
                questions = self._generate_quiz_with_gemini(
                    module_title=module_title,
                    roadmap_title=roadmap_title,
                    quiz_mode=quiz_mode,
                    topics=topics,
                    note_excerpts=note_excerpts,
                    mistakes=mistakes,
                    question_count=question_count,
                )
                return {
                    "questions": questions,
                    "source": "gemini",
                    "model": self.model,
                    "note": "",
                }
            except Exception as exc:  # broad fallback by design
                fallback_questions = self._fallback_quiz(
                    module_title=module_title,
                    quiz_mode=quiz_mode,
                    topics=topics,
                    note_excerpts=note_excerpts,
                    mistakes=mistakes,
                    question_count=question_count,
                )
                return {
                    "questions": fallback_questions,
                    "source": "fallback",
                    "model": "",
                    "note": f"Gemini unavailable, fallback used: {exc}",
                }

        return {
            "questions": self._fallback_quiz(
                module_title=module_title,
                quiz_mode=quiz_mode,
                topics=topics,
                note_excerpts=note_excerpts,
                mistakes=mistakes,
                question_count=question_count,
            ),
            "source": "fallback",
            "model": "",
            "note": "",
        }

    def _generate_topics_with_gemini(self, *, module_title, roadmap_title, existing_topics, note_excerpts, count):
        prompt = (
            "You are generating a personalized study plan for one university module. "
            "Return strict JSON only with shape: "
            '{"topics":[{"title":"string","why_it_matters":"string"}]}. '
            f"Generate exactly {count} high-value study topics for the module. "
            "Topics must be specific, non-overlapping, and practical for quizzes and revision. "
            f"Module title: {module_title}. "
            f"Roadmap/course context: {roadmap_title or 'not provided'}. "
            f"User existing/custom topics (if any): {existing_topics or []}. "
            f"User notes excerpts (may include PDF notes): {note_excerpts[:4]}. "
            "Prioritize concepts supported by the user's notes when present. "
            "Avoid generic filler like 'introduction' or 'conclusion'."
        )
        data = self._request_gemini_json(prompt)
        topics = self._normalize_topics_payload(data.get("topics", []), count=count)
        if not topics:
            raise RuntimeError("Gemini returned no usable topics")
        return topics

    def _generate_quiz_with_gemini(self, *, module_title, roadmap_title, quiz_mode, topics, note_excerpts, mistakes, question_count):
        mode_instruction = {
            "mock_exam": "Create an exam-style mixed quiz covering the full module with balanced topic coverage and slightly harder questions.",
            "topic": "Create a focused quiz only for the provided topic(s) with direct mastery checks and quick feedback.",
            "practice": "Create a practice quiz covering all provided topics with extra focus on prior mistakes and spaced repetition.",
        }.get(quiz_mode, "Create a practice quiz.")
        prompt = (
            "Generate a personalized quiz for one university module using the user's topics, notes and past mistakes. "
            "Return strict JSON only with shape: "
            '{"questions":[{"topic":"string","question":"string","options":["a","b","c","d"],'
            '"correct_index":0,"explanation":"string"}]}. '
            f"Generate exactly {question_count} questions with 4 options each and one correct answer. "
            "Use varied difficulty, but focus more on repeated mistakes when relevant. "
            "Questions must test understanding, not pure memorization. "
            f"Quiz mode: {quiz_mode}. {mode_instruction} "
            f"Module title: {module_title}. "
            f"Roadmap/course context: {roadmap_title or 'not provided'}. "
            f"Topics: {topics[:20]}. "
            f"Notes excerpts: {note_excerpts[:4]}. "
            f"Mistake history (topic/question summaries): {mistakes[:12]}."
        )
        data = self._request_gemini_json(prompt)
        questions = self._normalize_quiz_payload(data.get("questions", []), topics=topics, module_title=module_title)
        if not questions:
            raise RuntimeError("Gemini returned no usable quiz questions")
        return questions[:question_count]

    def _request_gemini_json(self, prompt):
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=25) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Gemini HTTP {exc.code}: {body[:200]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Gemini network error: {exc.reason}") from exc

        text = self._extract_text_from_gemini(raw)
        return self._extract_json(text)

    def _extract_text_from_gemini(self, response):
        candidates = response.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        text_chunks = [part.get("text", "") for part in parts if part.get("text")]
        if not text_chunks:
            raise RuntimeError("Gemini response had no text")
        return "\n".join(text_chunks)

    def _extract_json(self, text):
        stripped = (text or "").strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
        if stripped.startswith("{"):
            return json.loads(stripped)
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("Gemini output did not contain a JSON object")
        return json.loads(stripped[start:end + 1])

    def _normalize_topics_payload(self, raw_topics, count=10):
        seen = set()
        topics = []
        for item in raw_topics or []:
            if isinstance(item, dict):
                title = _safe_text(item.get("title"), 160)
                why = _safe_text(item.get("why_it_matters"), 300)
            else:
                title = _safe_text(item, 160)
                why = ""
            if len(title) < 3:
                continue
            key = title.casefold()
            if key in seen:
                continue
            seen.add(key)
            topics.append({"id": _slug_key(title) or f"topic-{len(topics)+1}", "title": title, "why": why})
            if len(topics) >= count:
                break
        return topics

    def _normalize_quiz_payload(self, raw_questions, *, topics, module_title):
        topic_choices = topics or [module_title]
        normalized = []
        for idx, item in enumerate(raw_questions or []):
            if not isinstance(item, dict):
                continue
            question = _safe_text(item.get("question"), 500)
            if len(question) < 8:
                continue
            raw_options = item.get("options", [])
            if not isinstance(raw_options, list):
                continue
            options = [_safe_text(opt, 240) for opt in raw_options if _safe_text(opt, 240)]
            if len(options) < 4:
                continue
            options = options[:4]
            try:
                correct_index = int(item.get("correct_index", 0))
            except (TypeError, ValueError):
                correct_index = 0
            correct_index = _clamp(correct_index, 0, len(options) - 1)
            topic = _safe_text(item.get("topic"), 120) or topic_choices[idx % len(topic_choices)]
            explanation = _safe_text(item.get("explanation"), 1000)
            normalized.append(
                {
                    "id": f"q-{idx+1}",
                    "topic": topic,
                    "question": question,
                    "options": options,
                    "correct": correct_index,
                    "explanation": explanation or "Review the topic and compare each option carefully.",
                }
            )
        return normalized

    def _normalize_topic_titles(self, topics):
        result = []
        seen = set()
        for item in topics:
            title = ""
            if isinstance(item, dict):
                title = _safe_text(item.get("title"), 160)
            else:
                title = _safe_text(item, 160)
            if len(title) < 2:
                continue
            key = title.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(title)
        return result[:30]

    def _normalize_note_excerpts(self, notes):
        normalized = []
        for note in notes:
            if isinstance(note, dict):
                normalized.append(
                    {
                        "name": _safe_text(note.get("name"), 200),
                        "excerpt": _safe_text(note.get("excerpt"), 3000),
                    }
                )
            elif isinstance(note, str):
                normalized.append({"name": "", "excerpt": _safe_text(note, 3000)})
        return normalized[:8]

    def _normalize_mistakes(self, mistakes):
        normalized = []
        for item in mistakes:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "topic": _safe_text(item.get("topic"), 120),
                    "question": _safe_text(item.get("question"), 240),
                    "count": _clamp(int(item.get("count", 1) or 1), 1, 20),
                    "last_user_answer": _safe_text(item.get("last_user_answer") or item.get("user_answer"), 200),
                    "correct_answer": _safe_text(item.get("correct_answer"), 200),
                }
            )
        return normalized[:20]

    def _fallback_topics(self, *, module_title, existing_topics, note_excerpts, count):
        seeds = []
        seeds.extend(existing_topics)
        seeds.extend(self._keywords_from_notes(note_excerpts))
        seeds.extend(
            [
                "Core Concepts and Terminology",
                "Key Models and Frameworks",
                "Problem-Solving Techniques",
                "Worked Examples",
                "Common Mistakes and Misconceptions",
                "Real-World Applications",
                "Evaluation and Trade-offs",
                "Practice Questions Strategy",
                "Revision Checklist",
                "Exam-Style Scenarios",
                "Advanced Extensions",
                "Practical Implementation Workflow",
            ]
        )

        out = []
        seen = set()
        for seed in seeds:
            seed = _safe_text(seed, 160)
            if not seed:
                continue
            title = seed if module_title.lower() in seed.lower() else f"{module_title}: {seed}"
            key = title.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "id": _slug_key(title) or f"topic-{len(out)+1}",
                    "title": title,
                    "why": "Generated from your module context and notes fallback logic.",
                }
            )
            if len(out) >= count:
                break
        return out

    def _fallback_quiz(self, *, module_title, quiz_mode, topics, note_excerpts, mistakes, question_count):
        rng = random.Random()
        topic_pool = topics[:] if topics else [f"{module_title} Fundamentals"]
        mistake_topics = [m.get("topic") for m in mistakes if m.get("topic")]
        prioritized = [t for t in mistake_topics if t in topic_pool] + [t for t in topic_pool if t not in mistake_topics]
        if not prioritized:
            prioritized = topic_pool

        note_keywords = self._keywords_from_notes(note_excerpts)[:8]
        fallback_keywords = note_keywords or ["definitions", "examples", "trade-offs", "applications"]
        if quiz_mode == "mock_exam":
            fallback_keywords = (note_keywords or ["integration", "evaluation", "design", "analysis", "applications"])[:8]
        elif quiz_mode == "topic":
            fallback_keywords = (note_keywords or ["core concept", "common error", "application", "comparison"])[:6]

        questions = []
        for index in range(question_count):
            topic = prioritized[index % len(prioritized)]
            keyword = fallback_keywords[index % len(fallback_keywords)]
            if quiz_mode == "mock_exam":
                correct_answer = f"Integrate {topic} with related concepts, justify trade-offs, and test yourself with exam-style scenarios around {keyword}."
            elif quiz_mode == "topic":
                correct_answer = f"Practice {topic} with targeted examples, explain the reasoning, and correct common errors linked to {keyword}."
            else:
                correct_answer = f"Focus on {topic} by practicing with examples and explaining the concept in your own words."
            distractors = [
                f"Memorize isolated facts about {keyword} without practice.",
                f"Skip {topic} and move directly to advanced material.",
                f"Study only one solved example and avoid comparing alternatives.",
            ]
            options = [correct_answer] + distractors
            rng.shuffle(options)
            correct_index = options.index(correct_answer)

            question_text = (
                f"For the module '{module_title}', what is the best approach for the topic '{topic}' "
                f"when reviewing notes about {keyword} in {quiz_mode.replace('_', ' ')} mode?"
            )
            explanation = (
                "Active practice plus explanation improves retention and helps you correct recurring mistakes. "
                "Use your notes to compare concepts, not just memorize phrases."
            )

            questions.append(
                {
                    "id": f"q-{index+1}",
                    "topic": topic,
                    "question": question_text,
                    "options": options,
                    "correct": correct_index,
                    "explanation": explanation,
                }
            )
        return questions

    def _keywords_from_notes(self, note_excerpts):
        text = " ".join(_safe_text(note.get("excerpt"), 1000) for note in note_excerpts if isinstance(note, dict))
        words = re.findall(r"[A-Za-z][A-Za-z\\-]{3,}", text)
        stop = {
            "that", "this", "with", "from", "into", "your", "their", "there", "about", "which", "when",
            "where", "what", "have", "were", "been", "will", "would", "should", "could", "notes", "topic",
            "module", "using", "used", "than", "then", "also", "such", "these", "those", "between",
            "through", "because", "while", "each", "some", "many", "more", "most", "very", "make",
            "does", "done", "data", "information", "process", "system", "method",
        }
        counts = {}
        for word in words:
            lower = word.lower()
            if lower in stop:
                continue
            counts[lower] = counts.get(lower, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [word.replace("-", " ").title() for word, _count in ranked[:12]]
