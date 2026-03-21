import os
import re
from pathlib import Path

import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from models import ResumeScore, MasterResume


# Common tech terms dictionary (seed list — augmented by YAML skills/tags at runtime)
BASE_TECH_TERMS = {
    "python", "javascript", "typescript", "java", "go", "golang", "rust", "c++", "c#",
    "ruby", "php", "swift", "kotlin", "scala", "sql", "html", "css", "html/css",
    "node.js", "react.js", "react", "angular", "vue.js", "vue", "next.js", "nuxt.js",
    "express.js", "express", "nestjs", "fastapi", "django", "flask", "spring", "spring boot",
    "rails", "laravel", ".net", "asp.net",
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "dynamodb", "cassandra",
    "sqlite", "oracle", "sql server",
    "kafka", "rabbitmq", "bullmq", "sqs", "sns", "eventbridge", "nats",
    "docker", "kubernetes", "k8s", "terraform", "ansible", "jenkins", "github actions",
    "ci/cd", "aws", "gcp", "azure", "firebase", "heroku", "vercel",
    "s3", "ec2", "lambda", "ecs", "eks", "fargate", "cloudfront",
    "graphql", "rest", "rest api", "grpc", "websocket", "socket.io", "webrtc",
    "microservices", "monolith", "serverless", "event-driven",
    "redux", "zustand", "tailwindcss", "tailwind", "material ui", "bootstrap",
    "jest", "mocha", "pytest", "cypress", "playwright", "selenium",
    "git", "postman", "swagger", "openapi",
    "typeorm", "prisma", "sequelize", "mongoose", "sqlalchemy",
    "jwt", "oauth", "saml", "sso",
    "nginx", "apache", "caddy", "load balancing",
    "zod", "joi", "pydantic",
    "machine learning", "deep learning", "nlp", "computer vision",
    "agile", "scrum", "kanban", "jira", "confluence",
}


class ResumeScorer:
    """Local keyword + TF-IDF scoring engine for resume-JD matching."""

    def __init__(self, yaml_path: str):
        """Load master resume YAML. Raises FileNotFoundError if missing."""
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(
                f"master_resume.yaml not found at {yaml_path}. "
                f"Create it at ~/.naukri-mcp/master_resume.yaml"
            )

        with open(path) as f:
            raw = yaml.safe_load(f)

        # Validate schema
        self.resume_data = raw
        MasterResume(**raw)  # raises ValidationError if invalid

        # Extract all skills (from skills.items, flattened, lowercased)
        self.all_skills: set[str] = set()
        for cat in raw.get("skills", []):
            for item in cat.get("items", []):
                self.all_skills.add(item)
                self.all_skills.add(item.lower())

        # Extract all tags (from achievements across experience + projects)
        self.all_tags: set[str] = set()
        for section in ("experience", "projects"):
            for entry in raw.get(section, []):
                for ach in entry.get("achievements", []):
                    for tag in ach.get("tags", []):
                        self.all_tags.add(tag.lower())

        # Build the full tech dictionary (base + YAML skills + tags)
        self._tech_dict: set[str] = BASE_TECH_TERMS | {s.lower() for s in self.all_skills} | self.all_tags

        # Pre-build resume text for master scoring
        self._master_text = self._build_resume_text(raw)

        # Configurable weights
        self._keyword_weight = float(os.getenv("SCORE_KEYWORD_WEIGHT", "0.6"))

    def score(self, jd_text: str, tailored_text: str | None = None) -> ResumeScore:
        """Score resume against JD. If tailored_text provided, score that instead."""
        resume_text = tailored_text or self._master_text

        # Layer 1: Keyword matching
        jd_keywords = self._extract_jd_keywords(jd_text)
        resume_keywords = self._extract_jd_keywords(resume_text)
        matched = jd_keywords & resume_keywords
        keyword_score = len(matched) / max(len(jd_keywords), 1)

        # Layer 2: TF-IDF cosine similarity
        tfidf_score = self._tfidf_similarity(resume_text, jd_text)

        # Combined score
        tfidf_weight = 1.0 - self._keyword_weight
        overall = self._keyword_weight * keyword_score + tfidf_weight * tfidf_score

        # Gap analysis
        missing = jd_keywords - resume_keywords
        gap_analysis = self._build_gap_analysis(list(matched), list(missing))

        return ResumeScore(
            overall_score=round(overall, 4),
            keyword_score=round(keyword_score, 4),
            tfidf_score=round(tfidf_score, 4),
            matched_skills=sorted(matched),
            missing_skills=sorted(missing),
            gap_analysis=gap_analysis,
            recommendation=self._recommend(overall),
        )

    def _extract_jd_keywords(self, text: str) -> set[str]:
        """Extract tech skills/tools from text using dictionary matching."""
        normalized = text.lower()

        # Expand parentheticals: "AWS (S3, EC2, KMS)" -> adds s3, ec2, kms
        paren_pattern = re.compile(r'\(([^)]+)\)')
        for match in paren_pattern.finditer(normalized):
            inner = match.group(1)
            for part in re.split(r'[,;/]', inner):
                part = part.strip()
                if part:
                    normalized += f" {part}"

        found: set[str] = set()
        for term in self._tech_dict:
            # Use word boundary for short terms, substring for compound terms
            if len(term) <= 2:
                # Very short terms (e.g., "go", "c#") — need exact word boundary
                pattern = r'\b' + re.escape(term) + r'\b'
            elif '.' in term or '/' in term or '+' in term or '#' in term:
                # Compound terms like "node.js", "c++", "c#", "ci/cd"
                if term in normalized:
                    found.add(term)
                continue
            else:
                pattern = r'\b' + re.escape(term) + r'\b'

            if re.search(pattern, normalized):
                found.add(term)

        return found

    def _tfidf_similarity(self, text_a: str, text_b: str) -> float:
        """TF-IDF vectorization + cosine similarity between two texts."""
        try:
            tfidf = TfidfVectorizer(stop_words='english', min_df=1)
            matrix = tfidf.fit_transform([text_a, text_b])
            sim = cosine_similarity(matrix[0:1], matrix[1:2])[0][0]
            return float(sim)
        except ValueError:
            # Empty vocabulary (e.g., both texts are stop words only)
            return 0.0

    def _recommend(self, score: float) -> str:
        min_score = float(os.getenv("MIN_MATCH_SCORE", "0.50"))
        target_score = float(os.getenv("TARGET_ATS_SCORE", "0.70"))
        if score < min_score:
            return "skip"
        elif score >= target_score:
            return "apply_directly"
        else:
            return "tailor"

    def _build_gap_analysis(self, matched: list[str], missing: list[str]) -> str:
        """Generate human-readable gap analysis."""
        parts = []
        total = len(matched) + len(missing)
        ratio = len(matched) / max(total, 1)

        if ratio >= 0.7:
            parts.append("Strong match.")
        elif ratio >= 0.5:
            parts.append("Moderate match.")
        else:
            parts.append("Weak match.")

        if matched:
            parts.append(f"Matched: {', '.join(matched[:5])}")
            if len(matched) > 5:
                parts[-1] += f" (+{len(matched) - 5} more)"
        if missing:
            parts.append(f"Missing: {', '.join(missing[:5])}")
            if len(missing) > 5:
                parts[-1] += f" (+{len(missing) - 5} more)"

        return " ".join(parts)

    def _build_resume_text(self, data: dict) -> str:
        """Build a flat text representation of the YAML resume for TF-IDF."""
        parts = []
        parts.append(data.get("summary", {}).get("default", ""))
        for cat in data.get("skills", []):
            parts.append(" ".join(cat.get("items", [])))
        for exp in data.get("experience", []):
            parts.append(f"{exp.get('role', '')} at {exp.get('company', '')}")
            for ach in exp.get("achievements", []):
                parts.append(ach.get("text", ""))
        for proj in data.get("projects", []):
            parts.append(proj.get("name", ""))
            for ach in proj.get("achievements", []):
                parts.append(ach.get("text", ""))
        return " ".join(parts)
