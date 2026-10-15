# 🚀 TradosKiller CAT Tool

**TradosKiller** é uma CAT Tool profissional de alto desempenho desenvolvida para substituir o SDL Trados Studio em fluxos de trabalho com arquivos massivos, eliminando lentidão, crashes e limites de memória.

Compatibilidade nativa total com formatos do ecossistema SDL: **`.sdlproj`**, **`.sdlxliff`**, **`.sdltm`**, **`.tmx`** e integração avançada com **SLM (Small Language Models)** via Ollama.

---

## 🌟 Principais Recursos

### ⚡ Desempenho e Arquitetura Anti-Crash (x64)
- **Streaming Parsers (`lxml.iterparse`)**: Arquivos gigantes (>100.000 segmentos) são processados sem carregar todo o XML na memória RAM.
- **SQLite Translation Memory**: Banco de dados relacional embarcado ultrarrápido com Full-Text Search (FTS) e índices B-Tree.
- **UI Virtualizada (`QAbstractTableModel`)**: Renderização paginada em tempo real com carregamento sob demanda instantâneo.

### 🎯 Telas e Vistas Estilo SDL Trados Studio
1. **Projects View**:
   - Gestão completa de projetos com painel de filtros em tempo real.
   - Coluna de progresso visual com barras coloridas autenticadas (`ProgressBarCellWidget`).
   - Painel inferior de detalhes com abas: *Project Details*, *Confirmation Statistics*, *Analysis Statistics*, *Task History*, *Project Attributes*.
2. **Files View**:
   - Listagem com contagem rigorosa e separada de **Segments** e **Words**.
   - Status de tradução preciso e barras de progresso limitadas entre 0% e 100%.
   - Detalhes do ficheiro, estatísticas de análise por faixa de match (Context, Repetições, 100%, 95-99%, etc.).
3. **Editor View**:
   - Tabela bilíngue completa com cores de estado e badges de correspondência (100%, Fuzzy, MT, SLM).
   - **Review Bar**: Status com contadores dinâmicos (*Untranslated*, *Draft*, *Translated*, *Approved*, *Rejected*).
   - **Advanced Display Filter 2.0**: Filtro avançado por texto (origem/alvo), regex, faixa percentual, estados, e botão **Generate** para exportar apenas os segmentos filtrados.
4. **Translation Memories View**:
   - Inspeção, edição em lote e manutenção de arquivos `.sdltm` e `.tmx`.

### 🤖 SLM Studio (IA Neural Local)
- **Treinamento de SLM Específica**: Extração automática de pares de tradução de bancos `.sdltm` locais para dataset instrucional Alpaca.
- **Criação Automatizada de Modelos Ollama**: Geração de `Modelfile` otimizado para o domínio automotivo e criação com 1 clique (`ollama create`).
- **Sugestão e Tradução em Tempo Real**: Atalho `Ctrl+G` para traduzir o segmento atual com SLM local, além de sugestões inteligentes no painel de Matches.
- **Batch Task Pré-tradução**: Opção de fallback inteligente via SLM local para segmentos sem match exato na memória de tradução.

---

## 💻 Instalação Rápida no Windows

### Método 1: Instalador Automático de 1 Clique (Recomendado)
Basta dar dois cliques no arquivo:
```bat
Instalar-TradosKiller.bat
```
O script cuidará de:
1. Detectar o Python 3.10+ instalado no seu sistema.
2. Criar e configurar o ambiente virtual `.venv`.
3. Instalar todas as dependências automaticamente (`PySide6`, `lxml`, `python-docx`, `requests`, `pyinstaller`).
4. Criar o atalho **TradosKiller** na sua **Área de Trabalho** e no **Menu Iniciar** com ícone personalizado.

### Método 2: Manual via Linha de Comando
```bash
git clone https://github.com/Wir-thunder/TradosKiller.Core.git
cd TradosKiller.Core
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Método 3: Compilar Executável Autônomo (.exe)
Para gerar a versão empacotada sem necessidade de instalar Python:
```bash
python build_installer.py
```
O executável final será gerado em `dist/TradosKiller/TradosKiller.exe`.

Para compilar o instalador com assistente gráfico do Windows (Next -> Next -> Finish), utilize o script do Inno Setup em:
`installer/TradosKiller_Setup.iss`.

---

## 🧪 Testes Automatizados
O projeto conta com uma suíte abrangente de 22 testes automatizados cobrindo streaming, integridade de estatísticas, QA engine, SLM e ADF:
```bash
.venv\Scripts\python -m unittest tests/test_trados_full.py
```

---

## 📄 Licença
Distribuído sob licença proprietária para produtividade de tradução técnica e automotiva.
Desenvolvido por **Wir-thunder** (`icaro.trad@gmail.com`).
