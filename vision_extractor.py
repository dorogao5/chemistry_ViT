"""Vision-based chemistry extractor using Mistral ViT models."""

from __future__ import annotations

import base64
import re

from mistralai import ImageURLChunk, Mistral, TextChunk

from exceptions import ChemistryOCRError


SYSTEM_PROMPT_CHEMISTRY_VIT = (
    "You are a careful OCR assistant for chemistry textbooks and lab notes. "
    "Return clean Markdown only. STRICT FORMAT: \n"
    "- One reaction per line. Use: $REACTANTS → PRODUCTS$ optionally followed by a space and 'conditions: ...'.\n"
    "- Examples: \n  $I_{2} + 5Cl_{2} + 6H_{2}O = 2HIO_{3} + 10HCl $\n  $ 6NaOH + 3I_{2} → NaIO_{3} + 5NaI + 3H_{2}O$ conditions: 0°C\n  $1/2 I_{2} + (CO)_{4}FeI_{2} → FeI_{3} + 4CO$ conditions: hν, hexane\n"
    "- Put ANY reaction conditions (catalyst, temperature, solvent, light hν, Δ, pressure, etc.) AFTER the reaction as 'conditions: ...'. Never place them on the arrow or inside the equation.\n"
    "- Keep plain characters only (no Word Equation objects). Use plain digits for subscripts (H2O, CO2).\n"
    "- If the image has multiple columns, transcribe columns SEQUENTIALLY: finish the left column top→bottom, then the right column. Do NOT mix columns.\n"
    "- Do NOT include ```markdown or ``` code fences.\n"
    "- After each reaction line output a literal \\n (backslash-n) to mark a new line."
)


class VisionChemistryExtractor:
    """Use Mistral ViT (pixtral) models to extract Markdown from images with a chemistry-aware prompt."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key is required for ViT")
        self.client = Mistral(api_key=api_key)

    def extract_markdown(self, data: bytes, mime_type: str, model: str, system_prompt: str = SYSTEM_PROMPT_CHEMISTRY_VIT) -> str:
        if not data:
            raise ChemistryOCRError("Empty image payload")
        base64_url = f"data:{mime_type};base64,{base64.b64encode(data).decode()}"

        try:
            # Prefer Chat API for broader SDK compatibility
            response = self.client.chat.complete(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": [TextChunk(text=system_prompt)],
                    },
                    {
                        "role": "user",
                        "content": [
                            TextChunk(text="Extract Markdown as instructed."),
                            ImageURLChunk(image_url=base64_url),
                        ],
                    },
                ],
            )
        except Exception as exc:  # noqa: BLE001
            raise ChemistryOCRError(f"Vision request failed: {exc}") from exc

        # Extract text from chat response
        text: str | None = None
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            msg = getattr(choice, "message", None)
            if msg is not None:
                content = getattr(msg, "content", None)
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    collected: list[str] = []
                    for chunk in content:
                        if hasattr(chunk, "text") and getattr(chunk, "text"):
                            collected.append(chunk.text)
                    if collected:
                        text = "\n".join(collected)
        if not text and hasattr(response, "output_text"):
            text = getattr(response, "output_text")
        if not text:
            text = str(response)
        # Clean up markdown code block markers that model might include
        text = re.sub(r'^```markdown\s*\n?', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE)
        # Convert literal \n sequences to actual newlines for Word processing
        text = text.replace('\\n', '\n')
        # Normalize Windows-style newlines
        text = text.replace('\r\n', '\n')
        # Ensure a final newline at the end to preserve last line
        if not text.endswith('\n'):
            text = text + '\n'
        return text

    def refine_with_text_model(self, draft_markdown: str, model: str = "mistral-medium-latest") -> str:
        """Second-pass refinement using a text model to split glued reactions."""
        system_prompt = (
            "You are an editor for chemistry reactions. Split any glued reactions into separate lines.\n"
            "Rules:\n"
            "- Preserve all content and order; do not invent or drop tokens.\n"
            "- Exactly one reaction per line: $REACTANTS → PRODUCTS$ optionally followed by ' conditions: ...'.\n"
        )

        def call_model(model_name: str) -> str:
            resp = self.client.chat.complete(
                model=model_name,
                messages=[
                    {"role": "system", "content": [TextChunk(text=system_prompt)]},
                    {"role": "user", "content": [TextChunk(text=draft_markdown)]},
                ],
            )
            out: str | None = None
            if hasattr(resp, "choices") and resp.choices:
                msg = getattr(resp.choices[0], "message", None)
                if msg is not None:
                    content = getattr(msg, "content", None)
                    if isinstance(content, str):
                        out = content
                    elif isinstance(content, list):
                        segs = [c.text for c in content if hasattr(c, "text") and c.text]
                        if segs:
                            out = "\n".join(segs)
            if not out and hasattr(resp, "output_text"):
                out = getattr(resp, "output_text")
            return (out or str(resp)).strip()

        try:
            refined = call_model(model)
        except Exception:
            refined = call_model("mistral-small-latest")

        refined = re.sub(r'^```markdown\s*\n?', '', refined, flags=re.MULTILINE)
        refined = re.sub(r'\n?```\s*$', '', refined, flags=re.MULTILINE)
        refined = refined.replace('\\n', '\n')
        refined = refined.replace('\r\n', '\n')
        if not refined.endswith('\n'):
            refined += '\n'
        return refined

    @staticmethod
    def _postprocess_reactions(text: str) -> str:
        """Heuristics to enforce one reaction per line and merge all conditions explicitly.
        - Never drop tokens: move hν/hv, temps, solvents to conditions.
        - Split concatenated equations into separate lines.
        """

        def split_concatenated(line: str) -> str:
            # If the line contains multiple arrows/equals, insert newlines before all except the first
            m = re.search(r"(→|->|=)", line)
            if not m:
                return line
            head = line[: m.end()]
            rest = line[m.end():]
            # newline before every subsequent delimiter
            rest = re.sub(r"\s*(→|->|=)\s*", r"\n\1 ", rest)
            return head + rest

        def parse_conditions_from_line(raw: str) -> tuple[str, list[str]]:
            # Ensure a space before 'conditions:' if missing
            base = re.sub(r"(?<!\s)(conditions:)", r" \1", raw, flags=re.IGNORECASE)
            existing: list[str] = []
            m = re.search(r"^(.*?)(?:\s*conditions:\s*)(.*)$", base, flags=re.IGNORECASE)
            if m:
                base_part = m.group(1)
                tail = m.group(2).strip()
                # keep original tail items (do not lose information)
                if tail:
                    existing = [t.strip() for t in re.split(r",|;", tail) if t.strip()]
                base = base_part
            # extract inline conditions markers to add
            addl: list[str] = []
            # hν / hv including in brackets
            if re.search(r"\b(h[νv])\b|\[\s*h[νv]\s*\]", base, flags=re.IGNORECASE):
                addl.append("hν")
                base = re.sub(r"\[?\s*h[νv]\s*\]?", "", base, flags=re.IGNORECASE)
            # temperatures (support Cyrillic 'С')
            temps = re.findall(r"[±+\-]?\d+\s*°\s*[CС]", base)
            if temps:
                addl.extend(temps)
                base = re.sub(r"[±+\-]?\d+\s*°\s*[CС]", "", base)
            # common solvents/catalysts words (kept and also appended to conditions)
            solvent_words = [
                "бензол", "benzol", "benzene", "гексан", "hexane", "meCN", "acetonitrile",
                "толуол", "toluene", "ацетон", "acetone", "этанол", "ethanol",
            ]
            for w in solvent_words:
                pattern = r"(?i)\b" + re.escape(w) + r"\b"
                if re.search(pattern, base):
                    addl.append(w)
                    base = re.sub(pattern, "", base)
            # Compose final conditions list (existing first, then additions, de-duplicated)
            final_conditions = list(dict.fromkeys([c for c in existing + addl if c]))
            return re.sub(r"\s+", " ", base).strip(), final_conditions

        fixed_lines: list[str] = []
        for original_line in text.split("\n"):
            if not original_line.strip():
                fixed_lines.append("")
                continue
            # First split concatenated equations into multiple logical lines
            expanded = split_concatenated(original_line)
            parts = expanded.split("\n")
            for part in parts:
                base, conds = parse_conditions_from_line(part)
                if conds:
                    base = base.rstrip()
                    # Always reconstruct conditions section to avoid duplication/glue
                    fixed_lines.append(f"{base} conditions: {', '.join(conds)}")
                else:
                    fixed_lines.append(base)
        # Join lines preserving empty lines; ensure trailing newline for last reaction
        result = "\n".join(fixed_lines)
        if not result.endswith("\n"):
            result += "\n"
        return result
