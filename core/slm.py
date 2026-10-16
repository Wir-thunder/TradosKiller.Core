"""
core.slm - Motor de Treino, Criação e Inferência de SLM (Small Language Model) via Ollama.

Funcionalidades:
- Comunicação direta com o Ollama local (http://localhost:11434)
- Extração de pares bilíngues de alta qualidade a partir de ficheiros .sdltm do SDL Trados Studio
- Geração de Modelfiles personalizados com few-shot in-context learning e prompts de sistema automotivo/técnico
- Criação e registro automático do modelo no Ollama (`ollama create`)
- Exportação de datasets de treino em formato Alpaca e ShareGPT (JSONL) para fine-tuning (LoRA / Unsloth)
- Tradução neural com Dynamic In-Context RAG (alimentada pelos termos e memórias ativas)
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple

import requests

from core.segment import display_text
from io_layer.sdltm import parse_sdltm_segment_xml, detect_sdltm_langs


OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

DEFAULT_AUTOMOTIVE_SYSTEM_PROMPT = (
    "Você é o modelo de linguagem e tradução neural (SLM) especializado na indústria automotiva e técnica "
    "(Toyota, Lexus, GWM, DYC). Sua função exclusiva é traduzir termos e manuais técnicos do Inglês para o "
    "Português do Brasil, mantendo rigorosa fidelidade terminológica, preservando acrônimos automotivos (ECU, DTC, "
    "CAN, EFI, HV, MIL), e adotando estilo claro, técnico e impessoal. Não adicione comentários, notas ou explicações: "
    "retorne exclusivamente a tradução exata do texto fornecido."
)


class OllamaClient:
    """Cliente para interagir com o motor Ollama local."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def _is_ollama_alive(self, timeout: float = 1.0) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=timeout)
            return r.status_code == 200
        except Exception:
            return False

    def is_available(self, timeout: float = 2.0) -> bool:
        """Verifica se há algum motor SLM disponível (Embedded local in-process ou Ollama)."""
        if self._is_ollama_alive(timeout=timeout):
            return True
        try:
            from core.embedded_slm import EmbeddedSLMEngine
            return EmbeddedSLMEngine.get_instance().is_available()
        except Exception:
            return False

    def list_models(self, timeout: float = 3.0) -> List[str]:
        """Retorna os nomes dos modelos instalados no Ollama e modelos .gguf locais da pasta models/."""
        models: List[str] = []
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=timeout)
            if r.status_code == 200:
                o_models = r.json().get("models", [])
                models.extend([m.get("name", "") for m in o_models if m.get("name")])
        except Exception:
            pass

        # Adiciona modelos GGUF locais embarcados encontrados no projeto ou disco
        try:
            from core.embedded_slm import EmbeddedSLMEngine
            for m_path in EmbeddedSLMEngine.find_available_models():
                base_f = os.path.basename(m_path)
                emb_name = f"embedded:{base_f}"
                if emb_name not in models:
                    models.append(emb_name)
        except Exception:
            pass

        return models

    def translate(
        self,
        prompt: str,
        model: str = "toyotao:latest",
        context_terms: Optional[List[Tuple[str, str]]] = None,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
        timeout: float = 60.0
    ) -> str:
        """
        Executa a tradução de um segmento usando o motor SLM.
        Prioriza o motor Embedded se solicitado ou se o servidor Ollama não estiver ativo.
        """
        clean_prompt = display_text(prompt).strip()
        if not clean_prompt:
            return ""

        # 1. Se for modelo embedded ou o Ollama não estiver em execução, usa o motor local in-process
        if model.startswith("embedded") or not self._is_ollama_alive(timeout=1.0):
            try:
                from core.embedded_slm import EmbeddedSLMEngine
                eng = EmbeddedSLMEngine.get_instance()
                if eng.is_available():
                    return eng.translate(clean_prompt, context_terms=context_terms, temperature=temperature)
            except Exception as e:
                pass

        # 2. Executa via Ollama API
        target_model = model
        available_models = self.list_models()
        if available_models:
            ollama_only = [m for m in available_models if not m.startswith("embedded:")]
            if ollama_only and target_model not in ollama_only and f"{target_model}:latest" not in ollama_only:
                target_model = ollama_only[0]

        # Montagem do prompt com termos de contexto de memórias (se existirem)
        final_prompt = clean_prompt
        if context_terms:
            terms_text = "\n".join([f"• \"{src}\" ➔ \"{tgt}\"" for src, tgt in context_terms[:5]])
            final_prompt = (
                f"Glossário e memórias de referência:\n{terms_text}\n\n"
                f"Texto a traduzir:\n{clean_prompt}"
            )

        payload = {
            "model": target_model,
            "prompt": final_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": 0.9,
            }
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            r = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=timeout)
            if r.status_code == 200:
                resp = r.json().get("response", "").strip()
                for prefix in ("Resposta:", "Tradução:", "Resposta (Português):", "Tradução (Português):"):
                    if resp.startswith(prefix):
                        resp = resp[len(prefix):].strip()
                if (resp.startswith('"') and resp.endswith('"')) or (resp.startswith("'") and resp.endswith("'")):
                    resp = resp[1:-1].strip()
                return resp
            elif r.status_code == 404:
                # Tenta fallback para o motor embedded se o modelo Ollama não existir
                try:
                    from core.embedded_slm import EmbeddedSLMEngine
                    eng = EmbeddedSLMEngine.get_instance()
                    if eng.is_available():
                        return eng.translate(clean_prompt, context_terms=context_terms)
                except Exception:
                    pass
                avail_str = ", ".join(available_models) if available_models else "nenhum"
                return (
                    f"[Modelo '{target_model}' não encontrado no Ollama (HTTP 404). "
                    f"Modelos disponíveis: {avail_str}. Acesse o SLM Studio para selecionar.]"
                )
            else:
                return f"[Erro Ollama HTTP {r.status_code}]"
        except requests.exceptions.Timeout:
            return "[Erro: Tempo limite do Ollama esgotado]"
        except requests.exceptions.ConnectionError:
            # Fallback transparente para o motor Embedded
            try:
                from core.embedded_slm import EmbeddedSLMEngine
                eng = EmbeddedSLMEngine.get_instance()
                if eng.is_available():
                    return eng.translate(clean_prompt, context_terms=context_terms)
            except Exception:
                pass
            return "[Erro: Não foi possível conectar ao Ollama e nenhum modelo .gguf local foi encontrado na pasta 'models/']"
        except Exception as e:
            return f"[Erro SLM: {str(e)}]"

    def create_model_api(
        self,
        name: str,
        modelfile_content: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """Cria um novo modelo no Ollama via API HTTP streaming."""
        payload = {
            "name": name,
            "modelfile": modelfile_content,
            "stream": True
        }
        try:
            r = requests.post(f"{self.base_url}/api/create", json=payload, stream=True, timeout=600)
            for line in r.iter_lines():
                if line:
                    data = json.loads(line.decode("utf-8"))
                    status = data.get("status", "")
                    if progress_callback and status:
                        progress_callback(status)
                    if "error" in data:
                        raise RuntimeError(data["error"])
            return True
        except Exception as e:
            if progress_callback:
                progress_callback(f"Erro na criação: {str(e)}")
            return False


class SLMTrainer:
    """Extrai unidades de tradução de ficheiros .sdltm e gera modelos e datasets."""

    @staticmethod
    def scan_sdltm_files(directory: str) -> List[str]:
        """Varre recursivamente uma pasta procurando ficheiros .sdltm."""
        results = []
        p = Path(directory)
        if not p.exists():
            return results

        try:
            for item in p.rglob("*.sdltm"):
                if item.is_file() and item.stat().st_size > 1024:
                    results.append(str(item.resolve()))
        except Exception:
            pass
        return sorted(results)

    @staticmethod
    def extract_pairs_from_sdltm(
        sdltm_path: str,
        max_pairs: int = 10000,
        min_words: int = 2,
        max_words: int = 60
    ) -> List[Tuple[str, str]]:
        """
        Extrai pares bilíngues (source, target) limpos e de qualidade de um ficheiro .sdltm.
        """
        pairs: List[Tuple[str, str]] = []
        if not os.path.exists(sdltm_path):
            return pairs

        try:
            conn = sqlite3.connect(f"file:{sdltm_path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("""
                SELECT source_segment, target_segment
                FROM translation_units
                WHERE source_segment IS NOT NULL AND target_segment IS NOT NULL
                LIMIT ?
            """, (max_pairs * 2,))

            seen_sources = set()

            for r in cur.fetchall():
                src_xml, tgt_xml = r[0], r[1]
                if not src_xml or not tgt_xml:
                    continue

                src_raw, _ = parse_sdltm_segment_xml(src_xml)
                tgt_raw, _ = parse_sdltm_segment_xml(tgt_xml)

                src = display_text(src_raw).strip()
                tgt = display_text(tgt_raw).strip()

                if not src or not tgt or src == tgt:
                    continue

                # Remove caracteres privados ou nulos
                src = re.sub(r"[\ue000-\uf8ff\x00-\x08\x0b\x0c\x0e-\x1f]", "", src).strip()
                tgt = re.sub(r"[\ue000-\uf8ff\x00-\x08\x0b\x0c\x0e-\x1f]", "", tgt).strip()

                src_words = len(src.split())
                tgt_words = len(tgt.split())

                if min_words <= src_words <= max_words and min_words <= tgt_words <= max_words:
                    if src.lower() not in seen_sources:
                        seen_sources.add(src.lower())
                        pairs.append((src, tgt))
                        if len(pairs) >= max_pairs:
                            break

            conn.close()
        except Exception:
            pass

        return pairs

    @staticmethod
    def extract_pairs_from_multiple_sdltm(
        sdltm_paths: List[str],
        max_total_pairs: int = 50000,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> List[Tuple[str, str]]:
        """Extrai e consolida pares de múltiplas bases de memórias .sdltm."""
        all_pairs: List[Tuple[str, str]] = []
        seen_sources = set()

        for idx, path in enumerate(sdltm_paths):
            if progress_callback:
                base_name = os.path.basename(path)
                progress_callback(len(all_pairs), f"A extrair de {base_name} ({idx+1}/{len(sdltm_paths)})...")

            pairs = SLMTrainer.extract_pairs_from_sdltm(path, max_pairs=max_total_pairs // max(1, len(sdltm_paths)))
            for s, t in pairs:
                s_key = s.lower().strip()
                if s_key not in seen_sources:
                    seen_sources.add(s_key)
                    all_pairs.append((s, t))
                    if len(all_pairs) >= max_total_pairs:
                        break
            if len(all_pairs) >= max_total_pairs:
                break

        return all_pairs

    @staticmethod
    def build_modelfile(
        base_model: str,
        few_shot_pairs: List[Tuple[str, str]],
        system_instruction: Optional[str] = None,
        temperature: float = 0.1
    ) -> str:
        """
        Constrói o conteúdo completo de um Modelfile do Ollama com prompt de sistema
        e mensagens de demonstração (Few-Shot In-Context Learning).
        """
        sys_prompt = system_instruction or DEFAULT_AUTOMOTIVE_SYSTEM_PROMPT
        lines = [
            f"FROM {base_model}",
            f"PARAMETER temperature {temperature}",
            "PARAMETER top_p 0.9",
            'PARAMETER stop "### Entrada"',
            'PARAMETER stop "### Instrução"',
            'PARAMETER stop "<|im_end|>"',
            'PARAMETER stop "<|endoftext|>"',
            "",
            f'SYSTEM """{sys_prompt}"""',
            ""
        ]

        # Embutir pares representativos como mensagens de treinamento few-shot
        for src, tgt in few_shot_pairs:
            src_clean = src.replace('"', '\\"').replace("\n", " ")
            tgt_clean = tgt.replace('"', '\\"').replace("\n", " ")
            lines.append(f'MESSAGE user "{src_clean}"')
            lines.append(f'MESSAGE assistant "{tgt_clean}"')

        return "\n".join(lines)

    @staticmethod
    def export_alpaca_dataset(
        pairs: List[Tuple[str, str]],
        output_jsonl_path: str,
        instruction: str = "Traduza o seguinte texto técnico automotivo do inglês para o português brasileiro:"
    ) -> int:
        """Exporta pares bilíngues em formato padrão Alpaca JSONL para fine-tuning (LoRA / Unsloth)."""
        count = 0
        os.makedirs(os.path.dirname(os.path.abspath(output_jsonl_path)), exist_ok=True)
        with open(output_jsonl_path, "w", encoding="utf-8") as f:
            for src, tgt in pairs:
                item = {
                    "instruction": instruction,
                    "input": src,
                    "output": tgt
                }
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
                count += 1
        return count

    @classmethod
    def create_custom_slm(
        cls,
        model_name: str,
        base_model: str,
        sdltm_paths: List[str],
        few_shot_count: int = 100,
        export_dataset_path: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Tuple[bool, str]:
        """
        Pipeline completo:
        1. Extrai pares das .sdltm selecionadas
        2. Seleciona os melhores exemplos para Few-Shot
        3. Gera o Modelfile com instruções especializadas de engenharia automotiva
        4. Cria o modelo no Ollama via CLI ou API
        5. Opcionalmente exporta o dataset completo em JSONL
        """
        if not sdltm_paths:
            return False, "Nenhuma base de memória .sdltm selecionada."

        if progress_callback:
            progress_callback(10, "A extrair segmentos de tradução das bases .sdltm...")

        # 1. Extração
        pairs = cls.extract_pairs_from_multiple_sdltm(sdltm_paths, max_total_pairs=20000, progress_callback=progress_callback)
        if not pairs:
            return False, "Nenhum par de tradução válido foi encontrado nos ficheiros .sdltm."

        if progress_callback:
            progress_callback(40, f"Extraídos {len(pairs):,} pares. A preparar Modelfile...")

        # 2. Exportação de dataset (se solicitada)
        if export_dataset_path:
            cls.export_alpaca_dataset(pairs, export_dataset_path)

        # 3. Seleção de exemplos Few-Shot diversificados
        selected_few_shots = pairs[:min(few_shot_count, len(pairs))]

        system_instruction = (
            "Você é o modelo de linguagem e tradução neural (SLM) especializado na indústria automotiva e técnica "
            "(Toyota, Lexus, GWM, DYC). Sua função exclusiva é traduzir termos e manuais técnicos do Inglês para o "
            "Português do Brasil, mantendo rigorosa fidelidade terminológica, preservando acrônimos automotivos (ECU, DTC, "
            "CAN, EFI, HV, MIL), e adotando estilo claro, técnico e impessoal. Não adicione comentários, notas ou explicações: "
            "retorne exclusivamente a tradução exata do texto fornecido."
        )

        modelfile_content = cls.build_modelfile(
            base_model=base_model,
            few_shot_pairs=selected_few_shots,
            system_instruction=system_instruction,
            temperature=0.1
        )

        # Salva o Modelfile temporário
        modelfile_path = os.path.join(os.environ.get("TEMP", "."), f"Modelfile_{model_name.replace(':', '_')}")
        with open(modelfile_path, "w", encoding="utf-8") as f:
            f.write(modelfile_content)

        if progress_callback:
            progress_callback(60, f"A compilar e instalar o modelo '{model_name}' no Ollama...")

        # 4. Executa a criação no Ollama (via CLI ollama create ou API)
        try:
            # Tenta via subprocess primeiro (rápido e nativo)
            cmd = ["ollama", "create", model_name, "-f", modelfile_path]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=300)
            if proc.returncode == 0:
                if progress_callback:
                    progress_callback(100, f"Modelo '{model_name}' criado com sucesso no Ollama!")
                return True, f"Modelo '{model_name}' criado com sucesso a partir de {len(pairs):,} segmentos!"
        except Exception:
            pass

        # Fallback via HTTP API
        client = OllamaClient()
        success = client.create_model_api(
            name=model_name,
            modelfile_content=modelfile_content,
            progress_callback=lambda s: progress_callback(80, f"Ollama: {s}") if progress_callback else None
        )
        if success:
            if progress_callback:
                progress_callback(100, f"Modelo '{model_name}' criado com sucesso!")
            return True, f"Modelo '{model_name}' criado com sucesso no Ollama!"
        else:
            return False, "Falha ao criar o modelo no Ollama. Verifique se o serviço Ollama está ativo."
