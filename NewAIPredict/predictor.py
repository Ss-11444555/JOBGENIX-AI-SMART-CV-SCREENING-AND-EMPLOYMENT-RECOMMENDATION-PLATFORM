"""
Utility helpers for loading the pre-trained NewAIPredict models and running
resume-based job role and salary predictions. The models were trained with
scikit-learn 1.6.x, so we monkeypatch the missing `_RemainderColsList` class
when loading under the current runtime to keep unpickling compatible.
"""

import datetime
import os
import re
from typing import Dict, Optional

import numpy as np
import pandas as pd
from joblib import load

# ---- Compatibility patch for scikit-learn 1.6 pickles ----
try:
    from sklearn.compose import _column_transformer

    class _RemainderColsList(list):
        """Compat shim so 1.6.x pickles load on older/newer sklearn versions."""

    _column_transformer._RemainderColsList = _RemainderColsList
except Exception:
    # If sklearn is missing entirely, model loading will fail later and we log it.
    _column_transformer = None


# Point directly to the folder that contains the model files (this file lives in NewAIPredict/)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
JOB_MODEL_PATH = os.path.join(BASE_DIR, "job_role_classifier.pkl")
SALARY_MODEL_PATH = os.path.join(BASE_DIR, "salary_prediction_model.pkl")

_job_model = None
_salary_model = None


def _load_model(model_path: str):
    """
    Load a joblib model with safe fallback logging.
    """
    if not os.path.exists(model_path):
        print(f"[NewAIPredict] Model not found: {model_path}")
        return None
    try:
        return load(model_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[NewAIPredict] Failed to load model {model_path}: {exc}")
        return None


def _get_models():
    """
    Lazily load and cache the job role and salary models.
    """
    global _job_model, _salary_model
    if _job_model is None:
        _job_model = _load_model(JOB_MODEL_PATH)
        _ensure_column_transformer_attrs(_job_model)
        _ensure_tfidf_fitted(_job_model)
    if _salary_model is None:
        _salary_model = _load_model(SALARY_MODEL_PATH)
        _ensure_column_transformer_attrs(_salary_model)
        _ensure_tfidf_fitted(_salary_model)
    return _job_model, _salary_model


def _ensure_column_transformer_attrs(model):
    """
    Newer sklearn pickles expect ColumnTransformer to have _name_to_fitted_passthrough.
    Older sklearn (1.3) lacks it, causing attribute errors on predict.
    Add a noop attribute when missing.
    """
    try:
        from sklearn.compose import ColumnTransformer
        from sklearn.pipeline import Pipeline
    except Exception:
        return

    def patch_ct(ct):
        if isinstance(ct, ColumnTransformer) and not hasattr(ct, "_name_to_fitted_passthrough"):
            ct._name_to_fitted_passthrough = {}

    if isinstance(model, Pipeline):
        # Check all steps for ColumnTransformers
        for _, step in model.steps:
            if isinstance(step, ColumnTransformer):
                patch_ct(step)
                # also patch transformers inside the column transformer
                for _, trans, _cols in step.transformers:
                    patch_ct(trans)
    patch_ct(model)


def _ensure_tfidf_fitted(model):
    """
    On older sklearn, some pickled TFIDF objects lose fitted attributes.
    If idf_ is missing, set it to ones so predict() doesn't crash.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import Pipeline
        from sklearn.compose import ColumnTransformer
        import numpy as np
        from scipy.sparse import spdiags
    except Exception:
        return

    def patch_vec(vec):
        if not isinstance(vec, TfidfVectorizer):
            return
        if getattr(vec, "idf_", None) is not None:
            return
        vocab_size = len(getattr(vec, "vocabulary_", {}) or [])
        if vocab_size == 0:
            return
        # Set idf_ to ones and rebuild the diagonal matrix
        vec.idf_ = np.ones(vocab_size, dtype=float)
        try:
            vec._tfidf._idf_diag = spdiags(vec.idf_, 0, vocab_size, vocab_size)
        except Exception:
            pass

    def walk(obj):
        if isinstance(obj, Pipeline):
            for _, step in obj.steps:
                walk(step)
        elif isinstance(obj, ColumnTransformer):
            for _, trans, _cols in obj.transformers:
                walk(trans)
        else:
            patch_vec(obj)

    walk(model)
 
 
_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _parse_month_year_token(token: str) -> Optional[datetime.date]:
    """
    Parse dates like 05/2022, 5-2022, Jan 2022, January 2022, or just 2022.
    """
    if not token:
        return None
    stripped = token.strip().lower()
    if stripped in {"present", "now", "current"}:
        return datetime.date.today()

    normalized = stripped.replace(".", " ").replace("-", " ").replace("/", " ")
    parts = [p for p in normalized.split() if p]

    year = None
    month = None

    if len(parts) == 2:
        a, b = parts
        if a.isdigit() and len(b) == 4 and b.isdigit():
            m = int(a)
            y = int(b)
            if 1 <= m <= 12:
                month, year = m, y
        if a in _MONTHS and len(b) == 4 and b.isdigit():
            month, year = _MONTHS[a], int(b)
    elif len(parts) == 1 and parts[0].isdigit():
        y = int(parts[0])
        if 1900 <= y <= 2100:
            year = y
            month = 1

    if year and month:
        return datetime.date(year, month, 1)
    return None


def _estimate_experience_from_date_ranges(text: str) -> Optional[float]:
    if not text:
        return None
    pattern = re.compile(
        r"([a-z]{3,9}\s+\d{4}|[0-1]?\d[/-]\d{4}|\d{4})\s*(?:-|\u2013|\u2014|to|until|through)\s*([a-z]{3,9}\s+\d{4}|[0-1]?\d[/-]\d{4}|\d{4}|present|now|current)",
        flags=re.IGNORECASE,
    )
    total_months = 0
    for start_token, end_token in pattern.findall(text):
        start = _parse_month_year_token(start_token)
        end = _parse_month_year_token(end_token)
        if start and end:
            months = (end.year - start.year) * 12 + (end.month - start.month) + 1
            if months < 0:
                continue
            total_months += months
    if total_months:
        return round(total_months / 12, 2)
    return None


def _estimate_experience_from_date_ranges_v2(text: str) -> Optional[float]:
    """
    More tolerant date-range parser:
    - Supports month names (Jan 2020), numeric (01/2020), and year-only (2020)
    - Supports separators -, en dash, em dash, to, until, through
    """
    if not text:
        return None
    pattern = re.compile(
        r"([a-z]{3,9}\s+\d{4}|[0-1]?\d[/-]\d{4}|\d{4})\s*(?:-|\u2013|\u2014|to|until|through)\s*([a-z]{3,9}\s+\d{4}|[0-1]?\d[/-]\d{4}|\d{4}|present|now|current)",
        flags=re.IGNORECASE,
    )
    total_months = 0
    for start_token, end_token in pattern.findall(text):
        start = _parse_month_year_token(start_token)
        end = _parse_month_year_token(end_token)
        if start and end:
            months = (end.year - start.year) * 12 + (end.month - start.month) + 1
            if months < 0:
                continue
            total_months += months
    if total_months:
        return round(total_months / 12, 2)
    return None
def _estimate_experience_from_date_ranges_v2(text: str) -> Optional[float]:
    """
    More tolerant date-range parser:
    - Supports month names (Jan 2020), numeric (01/2020), and year-only (2020)
    - Supports separators -, –, —, to, until, through
    """
    if not text:
        return None
    pattern = re.compile(
        r"([a-z]{3,9}\s+\d{4}|[0-1]?\d[/-]\d{4}|\d{4})\s*(?:-|–|—|to|until|through)\s*([a-z]{3,9}\s+\d{4}|[0-1]?\d[/-]\d{4}|\d{4}|present|now|current)",
        flags=re.IGNORECASE,
    )
    total_months = 0
    for start_token, end_token in pattern.findall(text):
        start = _parse_month_year_token(start_token)
        end = _parse_month_year_token(end_token)
        if start and end:
            months = (end.year - start.year) * 12 + (end.month - start.month) + 1
            if months < 0:
                continue
            total_months += months
    if total_months:
        return round(total_months / 12, 2)
    return None


def _strip_education_sections(text: str) -> str:
    """
    Remove lines inside an Education section so degree dates don't inflate experience.
    """
    if not text:
        return ""
    lines = text.splitlines()
    keep = []
    in_edu = False
    boundary_headers = re.compile(
        r"^(experience|work experience|work|employment|professional|projects?|project experience|skills|certifications|summary|objective)\b",
        flags=re.IGNORECASE,
    )
    for line in lines:
        l = line.strip().lower()
        if re.match(r"^education\b", l):
            in_edu = True
            continue
        if in_edu and boundary_headers.match(l):
            in_edu = False
        if not in_edu:
            keep.append(line)
    return "\n".join(keep)


def estimate_experience_years(text: str, experience_level: Optional[str] = None) -> Optional[float]:
    """
    Rough heuristic to estimate years of experience from resume text or level label.
    """
    clean_text = _strip_education_sections(text or "")
    candidate_years = []
    range_estimate = _estimate_experience_from_date_ranges_v2(clean_text)
    if range_estimate is not None:
        candidate_years.append(range_estimate)
    if clean_text:
        matches = re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", clean_text, flags=re.IGNORECASE)
        if matches:
            try:
                candidate_years.append(float(max(float(m) for m in matches)))
            except Exception:
                pass
    if candidate_years:
        return float(max(candidate_years))

    if experience_level:
        level = experience_level.strip().lower()
        level_map = {
            "intern": 0,
            "entry": 1,
            "junior": 2,
            "associate": 3,
            "mid": 4,
            "mid-level": 4,
            "mid level": 4,
            "senior": 6,
            "lead": 8,
            "principal": 10,
            "director": 12,
        }
        for key, val in level_map.items():
            if key in level:
                return float(val)
    return None


def _build_feature_frame(resume_text: str, experience_years: Optional[float], detected_skills=None, education_entries=None):
    """
    Prepare a single-row DataFrame matching the model feature schema.
    """
    safe_text = resume_text or ""
    # Enrich text with extracted skills/education so the model gets structured hints
    if detected_skills:
        safe_text += "\nSKILLS: " + ", ".join(detected_skills)
    if education_entries:
        safe_text += "\nEDUCATION: " + " | ".join(education_entries)
    exp_value = experience_years if experience_years is not None else 0.0
    return pd.DataFrame(
        [
            {
                "Skills": safe_text,
                "Education": safe_text,
                "Experience_Years": float(exp_value),
            }
        ]
    )


def predict_job_and_salary(
    resume_text: str,
    experience_years: Optional[float] = None,
    experience_level: Optional[str] = None,
    detected_skills: Optional[list] = None,
    education_entries: Optional[list] = None,
) -> Optional[Dict[str, object]]:
    """
    Run both models on the provided resume text and return predictions.
    """

    def _extract_classes(model):
        """Return classifier classes_ from the model or its final step."""
        if hasattr(model, "classes_"):
            return getattr(model, "classes_", None)
        if hasattr(model, "named_steps"):
            for step in reversed(list(model.named_steps.values())):
                if hasattr(step, "classes_"):
                    return getattr(step, "classes_", None)
        if hasattr(model, "steps"):
            for _name, step in reversed(list(getattr(model, "steps") or [])):
                if hasattr(step, "classes_"):
                    return getattr(step, "classes_", None)
        return None

    def _top_n_roles(model, features, n=3):
        """
        Return top-n job role predictions with probabilities, when available.
        """
        try:
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(features)
            else:
                proba = None
        except Exception:
            return []

        classes = _extract_classes(model)
        if proba is None or classes is None:
            return []

        try:
            scores = list(zip(classes, proba[0]))
            scores.sort(key=lambda item: float(item[1]), reverse=True)
            top = []
            for role, prob in scores[:n]:
                try:
                    prob_val = float(prob)
                except Exception:
                    prob_val = None
                top.append({"title": str(role), "probability": prob_val})
            return top
        except Exception:
            return []

    job_model, salary_model = _get_models()
    if not job_model and not salary_model:
        return None

    exp_years = experience_years
    if exp_years is None:
        exp_years = estimate_experience_years(resume_text, experience_level)

    features = _build_feature_frame(resume_text, exp_years, detected_skills, education_entries)

    job_role = None
    salary_pred = None
    top_job_roles = []

    try:
        if job_model:
            top_job_roles = _top_n_roles(job_model, features, n=3)
            job_role = job_model.predict(features)[0]
    except Exception as exc:  # noqa: BLE001
        print(f"[NewAIPredict] Job role prediction failed: {exc}")

    try:
        if salary_model:
            salary_pred = salary_model.predict(features)[0]
            # Convert numpy scalars to a native float
            if isinstance(salary_pred, (np.generic, np.ndarray)):
                salary_pred = float(np.array(salary_pred).item())
            elif salary_pred is not None:
                salary_pred = float(salary_pred)
    except Exception as exc:  # noqa: BLE001
        print(f"[NewAIPredict] Salary prediction failed: {exc}")

    return {
        "job_role": job_role,
        "salary": salary_pred,
        "experience_years": exp_years,
        "top_job_roles": top_job_roles,
        "education_detected": list(education_entries) if education_entries else [],
    }
