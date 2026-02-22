import json
from urllib import error, request

from django.conf import settings


def _clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, value))


class RoadmapGenerationService:
    """Generates roadmap graph data via Gemini when available with a deterministic fallback."""

    def __init__(self):
        self.api_key = getattr(settings, "GEMINI_API_KEY", "")
        self.model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")

    def generate(self, course_title, module_names=None, career_goal=""):
        if self.api_key:
            try:
                graph = self._generate_with_gemini(course_title, module_names or [], career_goal)
                return graph, "gemini", ""
            except Exception as exc:  # broad by design to guarantee a roadmap response
                fallback = self._generate_fallback(course_title, module_names or [], career_goal)
                note = f"Gemini unavailable, fallback used: {exc}"
                return fallback, "fallback", note

        return self._generate_fallback(course_title, module_names or [], career_goal), "fallback", ""

    def _generate_with_gemini(self, course_title, module_names, career_goal):
        prompt = self._build_prompt(course_title, module_names, career_goal)
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
            with request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Gemini HTTP {exc.code}: {body[:120]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Gemini network error: {exc.reason}") from exc

        text = self._extract_text_from_gemini(data)
        parsed = self._extract_json(text)
        return self._normalize_graph(parsed, module_names)

    def _build_prompt(self, course_title, module_names, career_goal):
        module_line = ", ".join(module_names) if module_names else "none"
        return (
            "Generate a student learning roadmap graph as JSON. "
            "The roadmap should contain modules and topics for a university student. "
            "Dependencies must include influence 0..1 showing how much earlier module impacts later modules. "
            f"Course title: {course_title}. "
            f"Preferred modules: {module_line}. "
            f"Career goal: {career_goal or 'not provided'}. "
            "Return strict JSON with this schema: "
            "{\"modules\":[{\"title\":str,\"description\":str,\"topics\":[{\"title\":str,\"description\":str,\"impact_weight\":float}],"
            "\"depends_on\":[{\"module\":str,\"influence\":float,\"rationale\":str}]}]}. "
            "Use 5-8 modules and 3-6 topics per module."
        )

    def _extract_text_from_gemini(self, response):
        candidates = response.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        text_chunks = [part.get("text", "") for part in parts if part.get("text")]
        if not text_chunks:
            raise RuntimeError("Gemini response did not include text content")
        return "\n".join(text_chunks)

    def _extract_json(self, text):
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()

        if stripped.startswith("{"):
            return json.loads(stripped)

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("Gemini output did not contain JSON object")
        return json.loads(stripped[start : end + 1])

    def _normalize_graph(self, raw_graph, preferred_module_names):
        modules = raw_graph.get("modules", []) if isinstance(raw_graph, dict) else []
        normalized = []

        for index, module in enumerate(modules):
            if not isinstance(module, dict):
                continue
            title = str(module.get("title", "")).strip() or f"Module {index + 1}"
            description = str(module.get("description", "")).strip()

            raw_topics = module.get("topics", [])
            topics = []
            if isinstance(raw_topics, list):
                for t_index, topic in enumerate(raw_topics):
                    if not isinstance(topic, dict):
                        continue
                    t_title = str(topic.get("title", "")).strip() or f"{title} Topic {t_index + 1}"
                    t_description = str(topic.get("description", "")).strip()
                    raw_weight = topic.get("impact_weight", 0.0)
                    try:
                        impact_weight = _clamp(float(raw_weight))
                    except (TypeError, ValueError):
                        impact_weight = 0.0
                    topics.append(
                        {
                            "title": t_title,
                            "description": t_description,
                            "impact_weight": impact_weight,
                        }
                    )

            if not topics:
                topics = self._default_topics_for_module(title)

            raw_depends = module.get("depends_on", [])
            depends_on = []
            if isinstance(raw_depends, list):
                for dep in raw_depends:
                    if not isinstance(dep, dict):
                        continue
                    dep_module = str(dep.get("module", "")).strip()
                    if not dep_module:
                        continue
                    try:
                        influence = _clamp(float(dep.get("influence", 0.0)))
                    except (TypeError, ValueError):
                        influence = 0.0
                    depends_on.append(
                        {
                            "module": dep_module,
                            "influence": influence,
                            "rationale": str(dep.get("rationale", "")).strip(),
                        }
                    )

            normalized.append(
                {
                    "title": title,
                    "description": description,
                    "topics": topics,
                    "depends_on": depends_on,
                }
            )

        if not normalized:
            return self._generate_fallback("", preferred_module_names, "")

        return {"modules": normalized}

    def _generate_fallback(self, course_title, module_names, career_goal):
        module_titles = module_names or self._infer_default_modules(course_title)

        modules = []
        for index, title in enumerate(module_titles):
            depends_on = []
            if index > 0:
                depends_on.append(
                    {
                        "module": module_titles[index - 1],
                        "influence": _clamp(0.45 - (index * 0.03)),
                        "rationale": "Builds directly on concepts from the previous module.",
                    }
                )

            modules.append(
                {
                    "title": title,
                    "description": self._module_description(title, career_goal),
                    "topics": self._default_topics_for_module(title),
                    "depends_on": depends_on,
                }
            )

        self._inject_common_dependency_rules(modules)
        return {"modules": modules}

    def _infer_default_modules(self, course_title):
        title = course_title.lower()
        if any(k in title for k in ["computer", "software", "cs", "data"]):
            return [
                "Programming Foundations",
                "Mathematics for Computing",
                "Data Structures and Algorithms",
                "Databases",
                "Software Engineering",
                "Data Science",
                "Career Preparation",
            ]
        if any(k in title for k in ["business", "management", "finance"]):
            return [
                "Business Fundamentals",
                "Quantitative Analysis",
                "Markets and Strategy",
                "Operations and Analytics",
                "Leadership and Communication",
                "Capstone Project",
                "Career Preparation",
            ]
        return [
            "Core Foundations",
            "Analytical Methods",
            "Applied Practice",
            "Intermediate Concepts",
            "Advanced Topics",
            "Industry Project",
            "Career Preparation",
        ]

    def _module_description(self, module_title, career_goal):
        if career_goal:
            return f"Builds competency in {module_title.lower()} for the goal: {career_goal}."
        return f"Builds competency in {module_title.lower()} and links it to future modules."

    def _default_topics_for_module(self, module_title):
        title = module_title.lower()
        if "math" in title:
            return [
                {"title": "Linear Algebra", "description": "Vectors, matrices, and transformations.", "impact_weight": 0.8},
                {"title": "Calculus", "description": "Rates of change and optimization.", "impact_weight": 0.65},
                {"title": "Probability", "description": "Random variables and distributions.", "impact_weight": 0.75},
            ]
        if "data science" in title:
            return [
                {"title": "Data Wrangling", "description": "Prepare and clean real-world data.", "impact_weight": 0.7},
                {"title": "Statistical Modeling", "description": "Fit and evaluate predictive models.", "impact_weight": 0.8},
                {"title": "Model Evaluation", "description": "Measure performance and generalization.", "impact_weight": 0.7},
            ]
        if "programming" in title:
            return [
                {"title": "Control Flow", "description": "Conditionals, loops, and functions.", "impact_weight": 0.7},
                {"title": "Object-Oriented Design", "description": "Classes, objects, and modularity.", "impact_weight": 0.65},
                {"title": "Testing Basics", "description": "Unit tests and debugging workflows.", "impact_weight": 0.6},
            ]
        if "career" in title:
            return [
                {"title": "Portfolio Projects", "description": "Showcase practical outcomes.", "impact_weight": 0.6},
                {"title": "Interview Preparation", "description": "Technical and behavioral interview drills.", "impact_weight": 0.7},
                {"title": "CV and Applications", "description": "Targeted job application strategy.", "impact_weight": 0.5},
            ]

        return [
            {"title": "Foundational Concepts", "description": "Core ideas and terminology.", "impact_weight": 0.6},
            {"title": "Applied Exercises", "description": "Practice through structured tasks.", "impact_weight": 0.65},
            {"title": "Assessment and Reflection", "description": "Evaluate understanding and gaps.", "impact_weight": 0.55},
        ]

    def _inject_common_dependency_rules(self, modules):
        modules_by_title = {module["title"].lower(): module for module in modules}

        math_module = None
        for title, module in modules_by_title.items():
            if "math" in title or "linear algebra" in title:
                math_module = module
                break

        if not math_module:
            return

        for module in modules:
            lower_title = module["title"].lower()
            if "data science" not in lower_title:
                continue

            already_linked = any(
                dep["module"].lower() == math_module["title"].lower() for dep in module["depends_on"]
            )
            if already_linked:
                continue

            module["depends_on"].append(
                {
                    "module": math_module["title"],
                    "influence": 0.8,
                    "rationale": "Linear algebra and probability are heavily used in data science methods.",
                }
            )
