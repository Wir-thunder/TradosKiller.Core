"""
io_layer.sdlproj - parser for SDL Trados project files (.sdlproj).

SDL project files are XML-based and contain:
- Project metadata (name, languages, creation date)
- List of project files with their paths and types
- Language pairs and translation memory settings

This parser extracts the relevant information to open projects in CAT Tool.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple
from xml.etree import ElementTree as ET

from core.project import Project, ProjectFile


# SDL project namespace
SDL_NS = {"sdl": "http://sdl.com/FileTypes/SdlProject/1.0"}


def parse_sdlproj(path: str) -> Optional[Project]:
    """
    Parse an SDL Trados project file and return a Project object with full file metadata and statistics.
    Returns None if parsing fails or file is invalid.
    """
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        proj_dir = Path(path).parent
        
        # Helper to find tag with or without namespace
        def find_elem(parent, tag_name):
            for child in parent:
                if child.tag == tag_name or child.tag.endswith(f"}}{tag_name}"):
                    return child
            return None

        def find_all_elems(parent, tag_name):
            res = []
            for child in parent.iter():
                if child.tag == tag_name or child.tag.endswith(f"}}{tag_name}"):
                    res.append(child)
            return res

        # 1. Project Info
        project_name = Path(path).stem
        created_at = ""
        status = "In Progress"
        gen_info = find_elem(root, "GeneralProjectInfo")
        if gen_info is not None:
            project_name = gen_info.attrib.get("Name", project_name)
            created_at = gen_info.attrib.get("CreatedAt", "")
            raw_status = gen_info.attrib.get("Status", "In Progress")
            status = "Completed" if raw_status == "Completed" else "In Progress"
        else:
            name_elem = root.find(".//sdl:Name", SDL_NS)
            if name_elem is not None and name_elem.text:
                project_name = name_elem.text

        # 2. Languages
        src_lang = ""
        tgt_lang = ""
        lang_dirs = find_all_elems(root, "LanguageDirection")
        if lang_dirs:
            first = lang_dirs[0]
            src_lang = first.attrib.get("SourceLanguageCode", "")
            tgt_lang = first.attrib.get("TargetLanguageCode", "")
            if not src_lang:
                s_elem = first.find("SourceLanguage") or first.find("sdl:SourceLanguage", SDL_NS)
                src_lang = s_elem.text if s_elem is not None else ""
            if not tgt_lang:
                t_elem = first.find("TargetLanguage") or first.find("sdl:TargetLanguage", SDL_NS)
                tgt_lang = t_elem.text if t_elem is not None else ""

        if not src_lang:
            s_elem = find_elem(root, "SourceLanguageCode") or root.find(".//sdl:SourceLanguage", SDL_NS)
            src_lang = s_elem.text if s_elem is not None and s_elem.text else "en-US"
        if not tgt_lang:
            tgt_lang = "pt-BR"

        project = Project(
            name=project_name,
            path=str(path),
            location=str(proj_dir),
            created=created_at,
            status=status,
            source_lang=src_lang,
            target_lang=tgt_lang
        )

        # 3. Project Files (Trados Studio ProjectFiles section)
        files_added = set()
        pf_elems = find_all_elems(root, "ProjectFile")

        for pf in pf_elems:
            role = pf.attrib.get("Role", "Translatable")
            filter_id = pf.attrib.get("FilterDefinitionId", "SpreadsheetML v. 1")

            # Procure os LanguageFiles para o target_lang
            lang_files = find_all_elems(pf, "LanguageFile")
            chosen_lf = None
            for lf in lang_files:
                if lf.attrib.get("LanguageCode", "") == tgt_lang:
                    chosen_lf = lf
                    break
            if chosen_lf is None and lang_files:
                # Use o último language file (que costuma ser o target bilingue)
                chosen_lf = lang_files[-1]

            if chosen_lf is not None:
                # Extrai estatísticas de confirmação
                cs = find_elem(chosen_lf, "ConfirmationStatistics")
                total_words = 0
                total_segs = 0
                draft_words = 0
                trans_words = 0
                appr_words = 0
                rej_words = 0
                untrans_words = 0

                draft_segs = 0
                trans_segs = 0
                appr_segs = 0
                rej_segs = 0
                untrans_segs = 0

                if cs is not None:
                    for stat in cs:
                        w = int(stat.attrib.get("Words", 0))
                        s = int(stat.attrib.get("Segments", 0))
                        total_words += w
                        total_segs += s
                        stag = stat.tag.split("}")[-1]
                        if stag == "Draft":
                            draft_words += w
                            draft_segs += s
                        elif stag in ("Translated",):
                            trans_words += w
                            trans_segs += s
                        elif stag in ("ApprovedTranslation", "ApprovedSignOff"):
                            appr_words += w
                            appr_segs += s
                        elif stag in ("RejectedTranslation", "RejectedSignOff"):
                            rej_words += w
                            rej_segs += s
                        elif stag in ("Unspecified",):
                            untrans_words += w
                            untrans_segs += s

                # Extrai estatísticas de análise (AnalysisStatistics)
                ans = find_elem(chosen_lf, "AnalysisStatistics")
                match_rep_words = 0
                match_rep_segs = 0
                match_perf_words = 0
                match_perf_segs = 0
                match_ctx_words = 0
                match_ctx_segs = 0
                match_100_words = 0
                match_100_segs = 0
                match_95_99_words = 0
                match_95_99_segs = 0
                match_85_94_words = 0
                match_85_94_segs = 0
                match_75_84_words = 0
                match_75_84_segs = 0
                match_50_74_words = 0
                match_50_74_segs = 0
                match_new_words = 0
                match_new_segs = 0

                if ans is not None:
                    rep_el = find_elem(ans, "Repetitions")
                    if rep_el is not None:
                        match_rep_words = int(rep_el.attrib.get("Words", 0))
                        match_rep_segs = int(rep_el.attrib.get("Segments", 0))
                    perf_el = find_elem(ans, "Perfect")
                    if perf_el is not None:
                        match_perf_words = int(perf_el.attrib.get("Words", 0))
                        match_perf_segs = int(perf_el.attrib.get("Segments", 0))
                    ctx_el = find_elem(ans, "InContextExact")
                    if ctx_el is not None:
                        match_ctx_words = int(ctx_el.attrib.get("Words", 0))
                        match_ctx_segs = int(ctx_el.attrib.get("Segments", 0))
                    ex_el = find_elem(ans, "Exact")
                    if ex_el is not None:
                        match_100_words = int(ex_el.attrib.get("Words", 0))
                        match_100_segs = int(ex_el.attrib.get("Segments", 0))
                    fuzzy_el = find_elem(ans, "Fuzzy")
                    if fuzzy_el is not None:
                        counts = find_all_elems(fuzzy_el, "CountData")
                        if len(counts) >= 1:
                            match_95_99_words = int(counts[0].attrib.get("Words", 0))
                            match_95_99_segs = int(counts[0].attrib.get("Segments", 0))
                        if len(counts) >= 2:
                            match_85_94_words = int(counts[1].attrib.get("Words", 0))
                            match_85_94_segs = int(counts[1].attrib.get("Segments", 0))
                        if len(counts) >= 3:
                            match_75_84_words = int(counts[2].attrib.get("Words", 0))
                            match_75_84_segs = int(counts[2].attrib.get("Segments", 0))
                        if len(counts) >= 4:
                            match_50_74_words = int(counts[3].attrib.get("Words", 0))
                            match_50_74_segs = int(counts[3].attrib.get("Segments", 0))
                    new_el = find_elem(ans, "New")
                    if new_el is not None:
                        match_new_words = int(new_el.attrib.get("Words", 0))
                        match_new_segs = int(new_el.attrib.get("Segments", 0))

                # Versão física do ficheiro
                f_versions = find_all_elems(chosen_lf, "FileVersion")
                if f_versions:
                    latest = f_versions[-1]
                    rel_phys = latest.attrib.get("PhysicalPath", "")
                    size_bytes = int(latest.attrib.get("Size", 0))
                    full_p = str(proj_dir / rel_phys)
                    if os.path.exists(full_p):
                        size_bytes = os.path.getsize(full_p)
                    
                    confirmed_w = trans_words + appr_words
                    confirmed_s = trans_segs + appr_segs
                    if total_words > 0 and confirmed_w > 0:
                        prog = max(0.0, min(100.0, (confirmed_w / total_words) * 100.0))
                    elif total_segs > 0 and confirmed_s > 0:
                        prog = max(0.0, min(100.0, (confirmed_s / total_segs) * 100.0))
                    else:
                        prog = 0.0

                    f_status = "Translated" if prog >= 100.0 else ("In Translation" if prog > 0 else "New")

                    proj_file = ProjectFile(
                        path=full_p,
                        file_type="sdlxliff",
                        source_lang=src_lang,
                        target_lang=tgt_lang,
                        words=total_words,
                        segment_count=total_segs,
                        translated_count=trans_segs,
                        draft_count=draft_segs,
                        approved_count=appr_segs,
                        rejected_count=rej_segs,
                        untranslated_count=untrans_segs,
                        translated_words=trans_words,
                        draft_words=draft_words,
                        approved_words=appr_words,
                        rejected_words=rej_words,
                        untranslated_words=untrans_words,
                        match_repetitions_words=match_rep_words,
                        match_repetitions_segs=match_rep_segs,
                        match_perfect_words=match_perf_words,
                        match_perfect_segs=match_perf_segs,
                        match_context_words=match_ctx_words,
                        match_context_segs=match_ctx_segs,
                        match_100_words=match_100_words,
                        match_100_segs=match_100_segs,
                        match_95_99_words=match_95_99_words,
                        match_95_99_segs=match_95_99_segs,
                        match_85_94_words=match_85_94_words,
                        match_85_94_segs=match_85_94_segs,
                        match_75_84_words=match_75_84_words,
                        match_75_84_segs=match_75_84_segs,
                        match_50_74_words=match_50_74_words,
                        match_50_74_segs=match_50_74_segs,
                        match_new_words=match_new_words,
                        match_new_segs=match_new_segs,
                        size_bytes=size_bytes,
                        status=f_status,
                        usage=role,
                        file_type_ident=filter_id,
                        last_modified=latest.attrib.get("FileTimeStamp", "")
                    )
                    project.files.append(proj_file)
                    files_added.add(full_p)

        # Fallback de busca em disco caso os arquivos não tenham sido declarados em ProjectFiles
        if not project.files:
            for ext in ("*.sdlxliff", "*.tmx"):
                for p in proj_dir.rglob(ext):
                    p_str = str(p)
                    if p_str not in files_added:
                        sz = os.path.getsize(p_str) if os.path.exists(p_str) else 0
                        project.files.append(ProjectFile(
                            path=p_str,
                            file_type="tmx" if p.suffix.lower() == ".tmx" else "sdlxliff",
                            source_lang=src_lang,
                            target_lang=tgt_lang,
                            size_bytes=sz
                        ))
                        files_added.add(p_str)

        # Extrai Translation Memories (.sdltm)
        for tp in find_all_elems(root, "MainTranslationProviderItem"):
            uri = tp.attrib.get("Uri", "")
            if "sdltm.file:///" in uri:
                rel = uri.split("sdltm.file:///")[-1].replace("/", os.sep)
                tm_abs = proj_dir / rel
                if tm_abs.exists() and str(tm_abs) not in project.tm_paths:
                    project.tm_paths.append(str(tm_abs))
            elif ".sdltm" in uri.lower():
                clean_path = uri.replace("file:///", "").replace("/", os.sep)
                tm_abs = Path(clean_path) if os.path.isabs(clean_path) else proj_dir / clean_path
                if tm_abs.exists() and str(tm_abs) not in project.tm_paths:
                    project.tm_paths.append(str(tm_abs))

        # Procura pastas comuns de TMs
        if not project.tm_paths and (proj_dir / "TMs").exists():
            for sdltm_file in (proj_dir / "TMs").glob("*.sdltm"):
                if str(sdltm_file) not in project.tm_paths:
                    project.tm_paths.append(str(sdltm_file))

        return project

    except Exception as e:
        print(f"Error parsing SDL project: {e}")
        return None


def parse_projects_xml(xml_path: Optional[str] = None) -> List[dict]:
    """
    Analisa o arquivo mestre projects.xml do SDL Trados Studio.
    Retorna lista de dicionários com dados resumidos de cada projeto.
    """
    search_paths = []
    if xml_path:
        search_paths.append(xml_path)
    
    docs = os.path.expanduser(r"~\Documents")
    for ver in ("Studio 2024", "Studio 2022", "Studio 2021", "Studio 2019"):
        p = os.path.join(docs, ver, "Projects", "projects.xml")
        search_paths.append(p)
    # Also direct default for user
    search_paths.append(r"C:\Users\Icaro\Documents\Studio 2021\Projects\projects.xml")

    found_path = None
    for sp in search_paths:
        if os.path.exists(sp):
            found_path = sp
            break

    if not found_path:
        return []

    try:
        tree = ET.parse(found_path)
        root = tree.getroot()
        results = []

        for p_elem in root.findall(".//ProjectListItem"):
            proj_path = p_elem.attrib.get("ProjectFilePath", "")
            guid = p_elem.attrib.get("Guid", "")
            info = p_elem.find("ProjectInfo")
            name = info.attrib.get("Name", Path(proj_path).stem) if info is not None else Path(proj_path).stem
            created_at = info.attrib.get("CreatedAt", "") if info is not None else ""
            raw_status = info.attrib.get("Status", "In Progress") if info is not None else "In Progress"
            created_by = info.attrib.get("CreatedBy", "") if info is not None else ""
            
            status_disp = "Completed" if raw_status == "Completed" else "In Progress"
            
            # Format date for display
            date_disp = ""
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    date_disp = dt.strftime("%d/%m/%Y %H:%M:%S")
                except Exception:
                    date_disp = created_at[:19].replace("T", " ")

            results.append({
                "guid": guid,
                "name": name,
                "path": proj_path,
                "status": status_disp,
                "due_date": "[none]",
                "created_at": date_disp,
                "type": "Studio project",
                "location": os.path.dirname(proj_path) if proj_path else "",
                "server": "(none)",
                "organization": "n/a",
                "created_by": created_by
            })

        return results
    except Exception as e:
        print(f"Error parsing projects.xml: {e}")
        return []



def detect_sdlproj_info(path: str) -> Tuple[str, str, str]:
    """
    Quick detection of SDL project info (name, source lang, target lang).
    Returns (name, source_lang, target_lang).
    """
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        
        name_elem = root.find(".//sdl:Name", SDL_NS)
        name = name_elem.text if name_elem is not None else Path(path).stem
        
        src_lang = ""
        tgt_lang = ""
        
        lang_pairs = root.findall(".//sdl:LanguagePairs/sdl:LanguageDirection", SDL_NS)
        if lang_pairs:
            first_pair = lang_pairs[0]
            src_lang_elem = first_pair.find("sdl:SourceLanguage", SDL_NS)
            tgt_lang_elem = first_pair.find("sdl:TargetLanguage", SDL_NS)
            src_lang = src_lang_elem.text if src_lang_elem is not None else ""
            tgt_lang = tgt_lang_elem.text if tgt_lang_elem is not None else ""
        
        return name, src_lang, tgt_lang
    
    except Exception:
        return Path(path).stem, "", ""


def is_sdlproj_file(path: str) -> bool:
    """Check if a file is an SDL project file."""
    return Path(path).suffix.lower() == ".sdlproj"
