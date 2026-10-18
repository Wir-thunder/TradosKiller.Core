"""
core.embedded_slm - Motor de SLM (Small Language Model) Embedded para o TradosKiller.

Executa inferência neural de tradução 100% in-process via llama-cpp-python:
- ZERO dependência de serviços externos ou daemon do Ollama
- Roda em qualquer máquina local sem necessidade de configuração de rede ou portas
- Carregamento de modelos .gguf diretamente da pasta 'models/' ou diretórios configurados
- Injeção dinâmica de terminologia e memórias SDLTM (RAG in-process)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import llama_cpp
    from llama_cpp import Llama
except ImportError:
    llama_cpp = None
    Llama = None

from core.segment import display_text


DEFAULT_SYSTEM_PROMPT = (
    "Você é um tradutor técnico e literário profissional especializado. "
    "Sua função é traduzir o texto do segmento original com fidelidade, precisão e fluência natural. "
    "Responda estritamente com a tradução final do texto, sem explicações, sem comentários, "
    "sem aspas desnecessárias e sem introduções como 'Tradução:' ou 'Aqui está:'."
)


class EmbeddedSLMEngine:
    """Motor de inferência de SLM executado diretamente dentro do TradosKiller."""

    _instance: Optional["EmbeddedSLMEngine"] = None
    _loaded_model: Optional[Llama] = None
    _loaded_path: Optional[str] = None

    def __init__(self, model_path: Optional[str] = None) -> None:
        self.active_model_path: Optional[str] = model_path
        if model_path and os.path.exists(model_path):
            self.load_model(model_path)
        else:
            # Tenta auto-descobrir o primeiro modelo disponível
            avail = self.find_available_models()
            if avail:
                self.active_model_path = avail[0]

    @classmethod
    def get_instance(cls) -> "EmbeddedSLMEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def is_engine_installed() -> bool:
        """Verifica se a biblioteca llama-cpp-python está instalada no ambiente."""
        return llama_cpp is not None

    @staticmethod
    def find_available_models(search_dirs: Optional[List[str]] = None) -> List[str]:
        """
        Descobre automaticamente ficheiros de modelo .gguf na pasta do projeto,
        no diretório do usuário ou em unidades externas (como D:\\).
        """
        dirs_to_check: List[str] = []

        if search_dirs:
            dirs_to_check.extend(search_dirs)

        # 1. Pasta models/ do projeto
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        project_models = os.path.join(base_dir, "models")
        if os.path.exists(project_models):
            dirs_to_check.append(project_models)

        # 2. Pasta do utilizador (.cat_workspace / .cat_tool / legada)
        user_home = os.path.expanduser("~")
        for u_dir in (".cat_workspace", ".cat_tool", ".tradoskiller"):
            u_models = os.path.join(user_home, u_dir, "models")
            if os.path.exists(u_models):
                dirs_to_check.append(u_models)

        # 3. Disco D: (caso exista pasta D:\models ou D:\)
        for d_cand in (r"D:\models", r"D:\SLM", r"D:\LLM"):
            if os.path.exists(d_cand):
                dirs_to_check.append(d_cand)

        discovered: List[str] = []
        for d in dirs_to_check:
            try:
                for root, _, files in os.walk(d):
                    for f in files:
                        if f.lower().endswith(".gguf"):
                            p = os.path.join(root, f)
                            if p not in discovered:
                                discovered.append(p)
            except Exception:
                pass

        # 4. Fallback: verifica se há blobs GGUF no cache do Ollama local
        ollama_blobs = os.path.join(user_home, ".ollama", "models", "blobs")
        if os.path.exists(ollama_blobs):
            try:
                for f in os.listdir(ollama_blobs):
                    blob_path = os.path.join(ollama_blobs, f)
                    if os.path.isfile(blob_path) and os.path.getsize(blob_path) > 100 * 1024 * 1024:
                        # Checa se tem o cabeçalho 'GGUF'
                        try:
                            with open(blob_path, "rb") as bf:
                                if bf.read(4) == b"GGUF":
                                    if blob_path not in discovered:
                                        discovered.append(blob_path)
                        except Exception:
                            pass
            except Exception:
                pass

        return discovered

    def is_available(self) -> bool:
        """Retorna True se o motor embedded estiver pronto para traduzir."""
        if not self.is_engine_installed():
            return False
        if self._loaded_model is not None:
            return True
        return len(self.find_available_models()) > 0

    def load_model(self, model_path: str, n_ctx: int = 1024, n_threads: int = 4) -> bool:
        """Carrega o modelo GGUF em memória."""
        if not self.is_engine_installed() or not os.path.exists(model_path):
            return False

        if self._loaded_path == model_path and self._loaded_model is not None:
            return True

        try:
            # Libera modelo anterior da memória se houver
            if self._loaded_model is not None:
                del self._loaded_model
                self._loaded_model = None

            self._loaded_model = Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_threads=n_threads,
                verbose=False
            )
            self._loaded_path = model_path
            self.active_model_path = model_path
            return True
        except Exception as e:
            return False

    def translate(
        self,
        prompt: str,
        context_terms: Optional[List[Tuple[str, str]]] = None,
        target_lang: str = "Português",
        temperature: float = 0.1,
        max_tokens: int = 256
    ) -> str:
        """
        Executa a tradução in-process do segmento usando o modelo GGUF embarcado.
        Injeta termos das memórias de tradução (RAG local).
        """
        clean_src = display_text(prompt).strip()
        if not clean_src:
            return ""

        if not self.is_engine_installed():
            return "[Erro: O motor embedded (llama-cpp-python) não está disponível]"

        # Garante carregamento do modelo
        if self._loaded_model is None:
            target_p = self.active_model_path
            if not target_p or not os.path.exists(target_p):
                avail = self.find_available_models()
                if not avail:
                    return "[Nenhum modelo .gguf encontrado na pasta 'models/' ou no sistema]"
                target_p = avail[0]

            ok = self.load_model(target_p)
            if not ok or self._loaded_model is None:
                return f"[Falha ao carregar o modelo embedded: {os.path.basename(target_p)}]"

        # Monta prompt otimizado de instrução de tradução
        glossary_part = ""
        if context_terms:
            terms_lines = [f"• \"{s}\" ➔ \"{t}\"" for s, t in context_terms[:5]]
            glossary_part = "Glossário obrigatório de termos das memórias:\n" + "\n".join(terms_lines) + "\n\n"

        full_prompt = (
            f"<|im_start|>system\n{DEFAULT_SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n"
            f"{glossary_part}"
            f"Traduza o seguinte texto para {target_lang}:\n"
            f"\"{clean_src}\"\n"
            f"Responda APENAS com o texto traduzido.<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        try:
            output = self._loaded_model(
                full_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=["<|im_end|>", "\n\nOriginal:", "\n\nTexto original:", "\n\nNota:", "Explicação:"]
            )
            raw_text = output["choices"][0]["text"].strip()
            return self._clean_model_output(raw_text)
        except Exception as e:
            return f"[Erro Embedded SLM: {str(e)}]"

    def _clean_model_output(self, resp: str) -> str:
        """Higieniza o texto gerado pela SLM para preencher a célula de tradução."""
        if not resp:
            return ""

        # Remove prefixos clássicos
        for prefix in (
            "Resposta:", "Tradução:", "Resposta (Português):", "Tradução (Português):",
            "A tradução é:", "A tradução em português é:", "A tradução para o português é:",
            "Tradução recomendada:"
        ):
            if resp.lower().startswith(prefix.lower()):
                resp = resp[len(prefix):].strip()

        # Remove aspas envolventes se o modelo tiver citado o texto
        if (resp.startswith('"') and resp.endswith('"')) or (resp.startswith("'") and resp.endswith("'")):
            resp = resp[1:-1].strip()

        # Remove eventuais seções de explicação que o modelo tenha adicionado abaixo
        if "\n\nExplicação:" in resp:
            resp = resp.split("\n\nExplicação:")[0].strip()
        if "\n\nNota:" in resp:
            resp = resp.split("\n\nNota:")[0].strip()

        return resp
