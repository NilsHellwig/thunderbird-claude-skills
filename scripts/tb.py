#!/usr/bin/env python3
"""tb.py - read-only access to local Thunderbird mail.

This tool only READS files that Thunderbird has already stored on disk.
It never sends, deletes, moves or modifies mail, never talks to a mail
server and never opens a network connection. The only file it ever writes
is its own acknowledgement marker (see ``acknowledge``), which lives
outside every Thunderbird profile.

Standard library only. Python 3.8+.
"""

import argparse
import configparser
import datetime as _dt
import email
import email.parser
import email.policy
import email.utils
import html
import json
import os
import re
import sqlite3
import sys
from html.parser import HTMLParser

__version__ = "0.1.0"

# Exit codes
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NEEDS_ACK = 3

# ---------------------------------------------------------------------------
# First-run acknowledgement
# ---------------------------------------------------------------------------

PRIVACY_NOTICE_HEAD = """\
PRIVACY NOTICE - thunderbird-mail skills (first run)

Every email these skills read is sent as context to the language model
that powers your agent. With a hosted model (for example Claude via the
Anthropic API) that means your mail content leaves this machine and is
processed by the model provider.

Recommendation: if your mail is confidential, run your agent against a
local or self-hosted open-source model. Claude Code works with any server
that speaks the Anthropic Messages API (set ANTHROPIC_BASE_URL).
"""

PRIVACY_NOTICE_TAIL = """
The skills never send, delete or modify mail and never contact a mail
server. They only read what Thunderbird already stored on this disk.

To continue, the user must explicitly agree. Then run:

    tb.py acknowledge
"""


# ---------------------------------------------------------------------------
# Local model detection (filesystem only - no request to any server)
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434"


def _ollama_extra_dirs():
    override = os.environ.get("TB_MAIL_OLLAMA_EXTRA_DIRS")
    if override is not None:
        return [d for d in override.split(os.pathsep) if d]
    home = os.path.expanduser("~")
    dirs = ["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin",
            "/Applications/Ollama.app/Contents/Resources",
            os.path.join(home, "Applications", "Ollama.app", "Contents", "Resources"),
            os.path.join(home, ".local", "bin")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(os.path.join(local, "Programs", "Ollama"))
    return dirs


def find_ollama_binary():
    names = ["ollama.exe", "ollama"] if sys.platform.startswith("win") else ["ollama"]
    dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d] + _ollama_extra_dirs()
    for d in dirs:
        for name in names:
            full = os.path.join(d, name)
            if os.path.isfile(full):
                return full
    return None


def _manifest_size(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return sum(int(layer.get("size", 0)) for layer in data.get("layers", []))
    except Exception:
        return 0


def list_ollama_models():
    """Locally installed Ollama models, read from the manifests on disk.

    Models tagged as cloud models run on remote servers and are skipped.
    """
    base = os.environ.get("OLLAMA_MODELS") or os.path.join(os.path.expanduser("~"), ".ollama", "models")
    root = os.path.join(base, "manifests")
    models = []
    if not os.path.isdir(root):
        return models
    for dirpath, _dirs, files in os.walk(root):
        for tag in files:
            rel = os.path.relpath(dirpath, root).replace("\\", "/").split("/")
            if len(rel) < 2:
                continue
            registry, repo = rel[0], "/".join(rel[1:])
            if registry == "registry.ollama.ai":
                name = repo[len("library/"):] if repo.startswith("library/") else repo
            else:
                name = registry + "/" + repo
            full = "%s:%s" % (name, tag)
            if "cloud" in tag.lower():
                continue
            models.append({"name": full, "size": _manifest_size(os.path.join(dirpath, tag))})
    models.sort(key=lambda m: (-m["size"], m["name"]))
    return models


def detect_local_llm():
    binary = find_ollama_binary()
    models = list_ollama_models()
    return {"ollama": binary, "models": models, "base_url": OLLAMA_URL,
            "suggested_model": models[0]["name"] if models else None}


def claude_command(model):
    if sys.platform.startswith("win"):
        return ('$env:ANTHROPIC_BASE_URL="%s"; $env:ANTHROPIC_AUTH_TOKEN="ollama"; '
                '$env:ANTHROPIC_API_KEY=""; claude --model %s' % (OLLAMA_URL, model))
    return ('ANTHROPIC_BASE_URL=%s ANTHROPIC_AUTH_TOKEN=ollama ANTHROPIC_API_KEY="" '
            'claude --model %s' % (OLLAMA_URL, model))


def _gb(size):
    return "%.1f GB" % (size / 1e9) if size else "size unknown"


def local_llm_section(info):
    lines = []
    if info["ollama"] and info["models"]:
        lines += ["", "LOCAL MODEL FOUND: Ollama is installed with these local models:"]
        lines += ["  - %s (%s)" % (m["name"], _gb(m["size"])) for m in info["models"][:10]]
        lines += [
            "",
            "To keep your mail on this machine, quit this session and start Claude Code",
            "against Ollama (make sure Ollama is running, e.g. the app or `ollama serve`):",
            "",
            "    " + claude_command(info["suggested_model"]),
            "",
            "Pick any model from the list; models with tool-calling support work best.",
            "Recent Ollama versions can also set this up for you: `ollama launch claude`.",
        ]
    elif info["ollama"]:
        lines += [
            "", "OLLAMA FOUND, but no local models are installed yet.",
            "Pull a model with tool-calling support (see https://ollama.com/search?c=tools),",
            "for example `ollama pull <model>`, then start Claude Code with:",
            "",
            "    " + claude_command("<model>"),
        ]
    else:
        lines += [
            "", "No local model runtime found. To run fully locally, install Ollama",
            "(https://ollama.com), pull a model with tool-calling support, and start",
            "Claude Code with:",
            "",
            "    " + claude_command("<model>"),
        ]
    return "\n".join(lines) + "\n"


def privacy_notice():
    return PRIVACY_NOTICE_HEAD + local_llm_section(detect_local_llm()) + PRIVACY_NOTICE_TAIL


def config_dir():
    override = os.environ.get("TB_MAIL_CONFIG_DIR")
    if override:
        return override
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "thunderbird-mail")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "thunderbird-mail")


def marker_path():
    return os.path.join(config_dir(), "acknowledged")


def is_acknowledged():
    return os.path.isfile(marker_path())


def write_ack_marker():
    """The single write operation in this tool. Creates the marker file."""
    path = marker_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("acknowledged %s\n" % _dt.datetime.now().isoformat(timespec="seconds"))
    return path


# ---------------------------------------------------------------------------
# Runtime read-only guard (Python audit hooks, 3.8+)
# ---------------------------------------------------------------------------

_WRITE_FLAGS = 0
for _name in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_APPEND", "O_TRUNC"):
    _WRITE_FLAGS |= getattr(os, _name, 0)

_BLOCKED_EVENTS = {
    "socket.__new__", "socket.connect", "socket.bind", "socket.getaddrinfo",
    "socket.gethostbyname", "socket.sendto", "smtplib.connect", "smtplib.send",
    "imaplib.open", "poplib.connect", "urllib.Request", "http.client.connect",
    "ftplib.connect", "nntplib.connect", "telnetlib.Telnet.open",
    "os.remove", "os.rename", "os.rmdir", "os.truncate", "os.chmod", "os.chown",
    "os.link", "os.symlink", "os.utime", "shutil.rmtree", "shutil.move",
    "shutil.copyfile", "subprocess.Popen", "os.system", "os.exec", "os.spawn",
    "os.posix_spawn", "os.startfile", "webbrowser.open",
}


class ReadOnlyViolation(RuntimeError):
    pass


def install_readonly_guard():
    """Abort the process on any network access or filesystem write.

    Writing is allowed only for the acknowledgement marker and its directory.
    """
    sys.dont_write_bytecode = True
    allowed_dir = os.path.normcase(os.path.abspath(config_dir()))

    def allowed(path):
        try:
            p = os.path.normcase(os.path.abspath(os.fsdecode(path)))
        except Exception:
            return False
        return p == allowed_dir or p.startswith(allowed_dir + os.sep)

    def hook(event, args):
        if event == "open":
            path, mode, flags = (list(args) + [None, None, None])[:3]
            writing = False
            if isinstance(mode, str):
                writing = any(c in mode for c in "wax+")
            elif isinstance(flags, int):
                writing = bool(flags & _WRITE_FLAGS)
            if writing and not allowed(path):
                raise ReadOnlyViolation("blocked write access to %r" % (path,))
        elif event == "os.mkdir":
            try:
                target = os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
            except Exception:
                target = ""
            is_parent = target and (allowed_dir + os.sep).startswith(target.rstrip(os.sep) + os.sep)
            if not (allowed(args[0]) or is_parent):
                raise ReadOnlyViolation("blocked mkdir %r" % (args[0],))
        elif event == "sqlite3.connect":
            target = str(args[0]) if args else ""
            if "mode=ro" not in target:
                raise ReadOnlyViolation("blocked non read-only sqlite connection")
        elif event in _BLOCKED_EVENTS or event.startswith("socket."):
            raise ReadOnlyViolation("blocked %s" % event)

    sys.addaudithook(hook)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


def thunderbird_homes():
    """Candidate Thunderbird base directories (containing profiles.ini)."""
    override = os.environ.get("TB_MAIL_THUNDERBIRD_HOME")
    if override:
        return [override]
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        cands = [os.path.join(home, "Library", "Thunderbird")]
    elif sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        cands = [os.path.join(appdata, "Thunderbird")]
    else:
        cands = [
            os.path.join(home, ".thunderbird"),
            os.path.join(home, "snap", "thunderbird", "common", ".thunderbird"),
            os.path.join(home, ".var", "app", "org.mozilla.Thunderbird", ".thunderbird"),
        ]
    return [c for c in cands if os.path.isfile(os.path.join(c, "profiles.ini"))]


def _read_ini(path):
    cp = configparser.RawConfigParser(strict=False)
    cp.optionxform = str
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        cp.read_file(fh)
    return cp


def list_profiles():
    profiles = []
    for base in thunderbird_homes():
        cp = _read_ini(os.path.join(base, "profiles.ini"))
        install_defaults = set()
        for sec in cp.sections():
            if sec.startswith("Install") and cp.has_option(sec, "Default"):
                install_defaults.add(cp.get(sec, "Default").replace("\\", "/"))
        for sec in cp.sections():
            if not sec.startswith("Profile") or not cp.has_option(sec, "Path"):
                continue
            rel = cp.get(sec, "Path")
            is_rel = cp.get(sec, "IsRelative", fallback="1") == "1"
            path = os.path.normpath(os.path.join(base, rel) if is_rel else rel)
            profiles.append({
                "name": cp.get(sec, "Name", fallback=os.path.basename(path)),
                "path": path,
                "active": rel.replace("\\", "/") in install_defaults,
                "default": cp.get(sec, "Default", fallback="0") == "1",
                "exists": os.path.isdir(path),
            })
    return profiles


def resolve_profile(args):
    if getattr(args, "profile_dir", None):
        path = os.path.abspath(os.path.expanduser(args.profile_dir))
        if not os.path.isdir(path):
            raise SystemExit("error: profile directory not found: %s" % path)
        return path
    profiles = [p for p in list_profiles() if p["exists"]]
    if not profiles:
        raise SystemExit(
            "error: no Thunderbird profile found. Pass --profile-dir PATH "
            "(the folder that contains prefs.js)."
        )
    wanted = getattr(args, "profile", None)
    if wanted:
        for p in profiles:
            if wanted in (p["name"], p["path"], os.path.basename(p["path"])):
                return p["path"]
        raise SystemExit("error: no profile named %r. Run `tb.py profiles`." % wanted)
    for key in ("active", "default"):
        for p in profiles:
            if p[key]:
                return p["path"]
    return profiles[0]["path"]


# ---------------------------------------------------------------------------
# prefs.js: accounts and identities
# ---------------------------------------------------------------------------

_PREF_RE = re.compile(r'^\s*user_pref\("([^"]+)",\s*(.*)\);\s*$')


def read_prefs(profile):
    prefs = {}
    path = os.path.join(profile, "prefs.js")
    if not os.path.isfile(path):
        return prefs
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _PREF_RE.match(line)
            if not m:
                continue
            raw = m.group(2).strip()
            try:
                prefs[m.group(1)] = json.loads(raw)
            except ValueError:
                prefs[m.group(1)] = raw
    return prefs


def own_addresses(prefs):
    out = set()
    for k, v in prefs.items():
        if k.startswith("mail.identity.") and k.endswith(".useremail") and isinstance(v, str):
            out.add(v.strip().lower())
    return out


def accounts(profile, prefs):
    """Return a list of {name, dir, store} for every mail server directory."""
    result = []
    seen = set()
    servers = sorted({k.split(".")[2] for k in prefs if k.startswith("mail.server.")})
    for srv in servers:
        pre = "mail.server.%s." % srv
        d = None
        rel = prefs.get(pre + "directory-rel")
        if isinstance(rel, str) and rel.startswith("[ProfD]"):
            d = os.path.join(profile, *rel[len("[ProfD]"):].split("/"))
        elif isinstance(prefs.get(pre + "directory"), str):
            d = prefs[pre + "directory"]
        if not d or not os.path.isdir(d):
            continue
        d = os.path.normpath(d)
        if d in seen:
            continue
        seen.add(d)
        store = prefs.get(pre + "storeContractID", "")
        name = prefs.get(pre + "name") or prefs.get(pre + "hostname") or os.path.basename(d)
        result.append({
            "name": str(name),
            "dir": d,
            "maildir": isinstance(store, str) and "maildir" in store,
        })
    # Fallback: scan Mail/ and ImapMail/ for directories prefs.js did not name.
    for top in ("Mail", "ImapMail"):
        base = os.path.join(profile, top)
        if not os.path.isdir(base):
            continue
        for entry in sorted(os.listdir(base)):
            d = os.path.normpath(os.path.join(base, entry))
            if os.path.isdir(d) and d not in seen:
                seen.add(d)
                result.append({"name": entry, "dir": d, "maildir": None})
    return result


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------

_SKIP_EXT = (".msf", ".dat", ".json", ".html", ".htm", ".sqlite", ".mab", ".log", ".bak", ".tmp")
_SKIP_NAMES = {".ds_store", "msgfilterrules.dat", "popstate.dat", "rules.dat", "thumbs.db"}

TRASH_NAMES = {"trash", "papierkorb", "deleted items", "deleted messages", "gelöschte elemente",
               "bin", "corbeille", "papelera", "cestino", "prullenbak"}
SENT_NAMES = {"sent", "sent mail", "sent messages", "sent items", "gesendet", "gesendete objekte",
              "gesendete elemente", "gesendete nachrichten", "envoyés", "enviados", "inviata",
              "posta inviata", "verzonden"}
INBOX_NAMES = {"inbox", "posteingang"}


def _is_maildir_folder(path):
    return os.path.isdir(os.path.join(path, "cur"))


def _walk_folders(directory, prefix, maildir_hint):
    out = []
    try:
        entries = sorted(os.listdir(directory))
    except OSError:
        return out
    for entry in entries:
        full = os.path.join(directory, entry)
        low = entry.lower()
        if low in _SKIP_NAMES or low.endswith(_SKIP_EXT) or entry.startswith("."):
            continue
        if entry.endswith(".sbd") and os.path.isdir(full):
            continue  # handled together with its parent folder
        if os.path.isfile(full) and maildir_hint is not True:
            out.append((prefix + entry, full, "mbox"))
        elif os.path.isdir(full) and _is_maildir_folder(full):
            out.append((prefix + entry, full, "maildir"))
        else:
            continue
        sub = full + ".sbd"
        if os.path.isdir(sub):
            out.extend(_walk_folders(sub, prefix + entry + "/", maildir_hint))
    return out


def all_folders(profile, prefs=None):
    prefs = read_prefs(profile) if prefs is None else prefs
    folders = []
    for acc in accounts(profile, prefs):
        for rel, path, kind in _walk_folders(acc["dir"], "", acc["maildir"]):
            leaf = rel.split("/")[-1].lower()
            folders.append({
                "path": acc["name"] + "/" + rel,
                "account": acc["name"],
                "name": rel.split("/")[-1],
                "file": path,
                "kind": kind,
                "trash": leaf in TRASH_NAMES or rel.lower() in ("[gmail]/trash", "[google mail]/trash"),
                "sent": leaf in SENT_NAMES,
                "inbox": leaf in INBOX_NAMES and "/" not in rel,
            })
    return folders


def select_folders(folders, pattern=None, include_trash=False, only=None):
    out = []
    pat = pattern.lower() if pattern else None
    for f in folders:
        if only == "sent" and not f["sent"]:
            continue
        if only == "inbox" and not f["inbox"]:
            continue
        if f["trash"] and not include_trash and not (pat and pat in f["path"].lower()):
            continue
        if pat and pat not in f["path"].lower():
            continue
        out.append(f)
    if pat:
        exact = [f for f in out if f["path"].lower() == pat]
        if exact:
            return exact
    return out


# ---------------------------------------------------------------------------
# Reading messages (read-only, own parser: mailbox.mbox opens files rb+)
# ---------------------------------------------------------------------------

_FROM_RE = re.compile(rb"^From (?:- |\S+ ).*\d\d:\d\d(?::\d\d)?")


def _is_separator(line, prev_blank, first):
    if not line.startswith(b"From "):
        return False
    return first or prev_blank or bool(_FROM_RE.match(line))


def iter_mbox(path):
    """Yield (offset, raw_bytes) for every message in an mbox file."""
    try:
        fh = open(path, "rb")
    except OSError:
        return
    with fh:
        offset = None
        chunks = []
        prev_blank = True
        pos = 0
        first = True
        for line in fh:
            if _is_separator(line, prev_blank, first):
                if offset is not None:
                    yield offset, b"".join(chunks)
                offset = pos
                chunks = []
            elif offset is not None:
                chunks.append(line)
            first = False
            prev_blank = line.strip() == b""
            pos += len(line)
        if offset is not None:
            yield offset, b"".join(chunks)


def read_mbox_at(path, offset):
    with open(path, "rb") as fh:
        fh.seek(offset)
        first_line = fh.readline()
        if not first_line.startswith(b"From "):
            return None
        chunks = []
        prev_blank = False
        for line in fh:
            if _is_separator(line, prev_blank, False):
                break
            chunks.append(line)
            prev_blank = line.strip() == b""
        return b"".join(chunks)


def iter_maildir(path):
    for sub in ("cur", "new"):
        d = os.path.join(path, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            full = os.path.join(d, name)
            if os.path.isfile(full):
                with open(full, "rb") as fh:
                    yield sub + "/" + name, fh.read()


def iter_folder(folder):
    if folder["kind"] == "maildir":
        for key, raw in iter_maildir(folder["file"]):
            yield "%s#%s" % (folder["path"], key), raw
    else:
        for off, raw in iter_mbox(folder["file"]):
            yield "%s#%d" % (folder["path"], off), raw


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_HEADER_PARSER = email.parser.BytesHeaderParser(policy=email.policy.default)


def _split_headers(raw):
    m = re.search(rb"\r?\n\r?\n", raw)
    return raw[: m.end()] if m else raw


def _hdr(msg, name):
    try:
        v = msg.get(name)
    except Exception:
        try:
            v = msg.get_all(name, failobj=[None])[0]
        except Exception:
            v = None
    if v is None:
        return ""
    try:
        return str(v)
    except Exception:
        return ""


def mozilla_flags(msg):
    """X-Mozilla-Status as int, or None when the header is absent."""
    value = _hdr(msg, "X-Mozilla-Status").strip()
    if not value:
        return None
    try:
        return int(value, 16)
    except ValueError:
        return None


def parse_date(value):
    if not value:
        return None
    try:
        d = email.utils.parsedate_to_datetime(value)
    except Exception:
        return None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d


def summarize(ref, raw, folder):
    msg = _HEADER_PARSER.parsebytes(_split_headers(raw))
    flags = mozilla_flags(msg)
    date = parse_date(_hdr(msg, "Date"))
    return {
        "ref": ref,
        "folder": folder["path"],
        "date": date.isoformat() if date else "",
        "_date": date,
        "from": _hdr(msg, "From"),
        "to": _hdr(msg, "To"),
        "cc": _hdr(msg, "Cc"),
        "subject": _hdr(msg, "Subject"),
        "message_id": _hdr(msg, "Message-ID").strip(),
        "in_reply_to": _hdr(msg, "In-Reply-To").strip(),
        "references": _hdr(msg, "References"),
        "unread": None if flags is None else not (flags & 0x0001),
        "deleted": bool(flags and flags & 0x0008),
        "has_body": bool(raw[len(_split_headers(raw)):].strip()),
    }


class _HTMLToText(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
             "blockquote", "table", "ul", "ol", "hr", "pre"}
    SKIP = {"script", "style", "head", "title"}

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK and tag != "li":
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(markup):
    p = _HTMLToText()
    try:
        p.feed(markup)
        p.close()
    except Exception:
        return html.unescape(re.sub(r"<[^>]+>", " ", markup))
    text = "".join(p.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _part_text(part):
    try:
        return part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except LookupError:
            return payload.decode("utf-8", errors="replace")


TEXT_ATTACHMENT_TYPES = {"text/plain", "text/csv", "text/calendar", "text/markdown"}
TEXT_ATTACHMENT_EXT = (".txt", ".csv", ".ics", ".md", ".vcf")


def full_message(ref, raw, folder):
    info = summarize(ref, raw, folder)
    info.pop("_date", None)
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    body = ""
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
    except Exception:
        part = None
    if part is not None:
        body = _part_text(part)
        if part.get_content_type() == "text/html":
            body = html_to_text(body)
    elif not msg.is_multipart():
        body = _part_text(msg)
        if msg.get_content_type() == "text/html":
            body = html_to_text(body)
    attachments = []
    try:
        atts = list(msg.iter_attachments())
    except Exception:
        atts = []
    for att in atts:
        name = att.get_filename() or ""
        ctype = att.get_content_type()
        try:
            payload = att.get_payload(decode=True) or b""
        except Exception:
            payload = b""
        entry = {"filename": name, "content_type": ctype, "size": len(payload)}
        if ctype in TEXT_ATTACHMENT_TYPES or name.lower().endswith(TEXT_ATTACHMENT_EXT):
            entry["text"] = _part_text(att)
        attachments.append(entry)
    info["body"] = body.strip()
    info["attachments"] = attachments
    if not info["has_body"]:
        info["body"] = ("[Body not available locally. Thunderbird has only stored the headers "
                        "for this message (e.g. IMAP folder without offline sync).]")
    return info


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def find_folder_by_path(folders, path):
    for f in folders:
        if f["path"] == path:
            return f
    return None


def load_ref(folders, ref):
    if "#" not in ref:
        return None, None
    fpath, key = ref.rsplit("#", 1)
    folder = find_folder_by_path(folders, fpath)
    if folder is None:
        return None, None
    if folder["kind"] == "maildir":
        full = os.path.join(folder["file"], *key.split("/"))
        if not os.path.isfile(full):
            return folder, None
        with open(full, "rb") as fh:
            return folder, fh.read()
    try:
        return folder, read_mbox_at(folder["file"], int(key))
    except (ValueError, OSError):
        return folder, None


def find_by_message_id(folders, msgid, include_trash):
    msgid = msgid.strip()
    if not msgid.startswith("<"):
        msgid = "<%s>" % msgid
    for folder in select_folders(folders, include_trash=include_trash):
        for ref, raw in iter_folder(folder):
            s = summarize(ref, raw, folder)
            if s["deleted"]:
                continue
            if s["message_id"] == msgid:
                return folder, ref, raw
    return None, None, None


def resolve_message(folders, ident, include_trash):
    folder, raw = load_ref(folders, ident)
    if raw is not None:
        return folder, ident, raw
    return find_by_message_id(folders, ident, include_trash)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def parse_when(value, end=False):
    if not value:
        return None
    m = re.match(r"^(\d+)([dwmy])$", value.strip())
    now = _dt.datetime.now(_dt.timezone.utc)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = n * {"d": 1, "w": 7, "m": 30, "y": 365}[unit]
        return now - _dt.timedelta(days=days)
    try:
        d = _dt.datetime.fromisoformat(value.strip())
    except ValueError:
        raise SystemExit("error: invalid date %r (use YYYY-MM-DD or e.g. 7d, 2w, 3m)" % value)
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.datetime.now().astimezone().tzinfo)
    if end and len(value.strip()) == 10:
        d = d + _dt.timedelta(days=1)
    return d


def _contains(hay, needle):
    return needle.lower() in (hay or "").lower()


def run_search(folders, args, only=None):
    since = parse_when(getattr(args, "since", None))
    until = parse_when(getattr(args, "until", None), end=True)
    results = []
    for folder in select_folders(folders, getattr(args, "folder", None),
                                 getattr(args, "include_trash", False), only=only):
        if getattr(args, "account", None) and not _contains(folder["account"], args.account):
            continue
        for ref, raw in iter_folder(folder):
            s = summarize(ref, raw, folder)
            if s["deleted"]:
                continue
            d = s["_date"]
            if since and (d is None or d < since):
                continue
            if until and (d is None or d >= until):
                continue
            if getattr(args, "unread", False) and s["unread"] is False:
                continue
            if getattr(args, "sender", None) and not _contains(s["from"], args.sender):
                continue
            if getattr(args, "recipient", None):
                rcpt = " ".join([s["to"], s["cc"], _hdr(_HEADER_PARSER.parsebytes(_split_headers(raw)), "Bcc")])
                if not _contains(rcpt, args.recipient):
                    continue
            if getattr(args, "subject", None) and not _contains(s["subject"], args.subject):
                continue
            if getattr(args, "text", None):
                if not _contains(s["subject"], args.text):
                    body = full_message(ref, raw, folder)
                    blob = body["body"] + " ".join(a.get("text", "") for a in body["attachments"])
                    if not _contains(blob, args.text):
                        continue
            results.append(s)
    epoch = _dt.datetime(1970, 1, 1, tzinfo=_dt.timezone.utc)
    results.sort(key=lambda r: r["_date"] or epoch, reverse=True)
    limit = getattr(args, "limit", 20)
    return results[:limit] if limit and limit > 0 else results


def search_index(profile, args):
    """Search Thunderbird's global search index (read-only)."""
    db = os.path.join(profile, "global-messages-db.sqlite")
    if not os.path.isfile(db):
        raise SystemExit("error: no global-messages-db.sqlite in this profile (global search disabled?)")
    uri = "file:%s?mode=ro&immutable=1" % _path_to_uri(db)
    con = sqlite3.connect(uri, uri=True)
    try:
        con.row_factory = sqlite3.Row
        where, params = ["m.deleted = 0"], []
        for col, val in (("c3author", args.sender), ("c4recipients", args.recipient),
                         ("c1subject", args.subject)):
            if val:
                where.append("t.%s LIKE ?" % col)
                params.append("%" + val + "%")
        if args.text:
            where.append("(t.c0body LIKE ? OR t.c1subject LIKE ?)")
            params += ["%" + args.text + "%"] * 2
        since = parse_when(args.since)
        until = parse_when(args.until, end=True)
        if since:
            where.append("m.date >= ?")
            params.append(int(since.timestamp() * 1000000))
        if until:
            where.append("m.date < ?")
            params.append(int(until.timestamp() * 1000000))
        sql = ("SELECT m.date AS date, m.headerMessageID AS mid, t.c1subject AS subject, "
               "t.c3author AS author, t.c4recipients AS recipients, f.name AS folder "
               "FROM messages m JOIN messagesText_content t ON t.docid = m.id "
               "LEFT JOIN folderLocations f ON f.id = m.folderID "
               "WHERE " + " AND ".join(where) + " ORDER BY m.date DESC LIMIT ?")
        params.append(args.limit if args.limit and args.limit > 0 else -1)
        try:
            rows = con.execute(sql, params).fetchall()
        except sqlite3.DatabaseError as exc:
            raise SystemExit("error: could not read the global search index: %s" % exc)
    finally:
        con.close()
    out = []
    for r in rows:
        d = _dt.datetime.fromtimestamp((r["date"] or 0) / 1000000, tz=_dt.timezone.utc)
        out.append({
            "ref": "<%s>" % r["mid"] if r["mid"] else "",
            "folder": r["folder"] or "",
            "date": d.isoformat(),
            "from": r["author"] or "",
            "to": r["recipients"] or "",
            "subject": r["subject"] or "",
            "message_id": "<%s>" % r["mid"] if r["mid"] else "",
            "unread": None,
        })
    return out


def _path_to_uri(path):
    p = os.path.abspath(path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return re.sub(r"[?#%]", lambda m: "%%%02X" % ord(m.group(0)), p)


# ---------------------------------------------------------------------------
# Thread
# ---------------------------------------------------------------------------

_MSGID_RE = re.compile(r"<[^<>\s]+>")


def build_thread(folders, ident, include_trash):
    folder, ref, raw = resolve_message(folders, ident, include_trash)
    if raw is None:
        raise SystemExit("error: message not found: %s" % ident)
    start = summarize(ref, raw, folder)
    if not start["message_id"]:
        return [full_message(ref, raw, folder)]
    by_id = {}
    for f in select_folders(folders, include_trash=include_trash):
        for r, rw in iter_folder(f):
            s = summarize(r, rw, f)
            if s["deleted"] or not s["message_id"]:
                continue
            s["_links"] = set(_MSGID_RE.findall(s["references"] + " " + s["in_reply_to"]))
            by_id.setdefault(s["message_id"], s)
    wanted = set(_MSGID_RE.findall(start["references"] + " " + start["in_reply_to"]))
    if start["message_id"]:
        wanted.add(start["message_id"])
    changed = True
    while changed:
        changed = False
        for mid, s in by_id.items():
            if mid in wanted:
                new = s["_links"] - wanted
            elif s["_links"] & wanted:
                new = {mid} | (s["_links"] - wanted)
            else:
                continue
            if new:
                wanted |= new
                changed = True
    msgs = [s for mid, s in by_id.items() if mid in wanted]
    epoch = _dt.datetime(1970, 1, 1, tzinfo=_dt.timezone.utc)
    msgs.sort(key=lambda r: r["_date"] or epoch)
    out = []
    for s in msgs:
        f, rw = load_ref(folders, s["ref"])
        out.append(full_message(s["ref"], rw, f))
    return out


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _clean(d):
    return {k: v for k, v in d.items() if not k.startswith("_")}


def emit(data, as_json):
    if as_json:
        if isinstance(data, list):
            data = [_clean(d) if isinstance(d, dict) else d for d in data]
        elif isinstance(data, dict):
            data = _clean(data)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(data)


def fmt_summary(s):
    flag = " [unread]" if s.get("unread") else ""
    date = (s.get("date") or "")[:16].replace("T", " ")
    return "%s%s\n  ref:     %s\n  folder:  %s\n  from:    %s\n  to:      %s\n  subject: %s" % (
        date or "(no date)", flag, s["ref"], s["folder"], s["from"], s["to"], s["subject"])


def fmt_full(m):
    lines = [
        "Ref:         " + m["ref"],
        "Folder:      " + m["folder"],
        "Date:        " + m["date"],
        "From:        " + m["from"],
        "To:          " + m["to"],
    ]
    if m["cc"]:
        lines.append("Cc:          " + m["cc"])
    lines += [
        "Subject:     " + m["subject"],
        "Message-ID:  " + m["message_id"],
    ]
    if m["in_reply_to"]:
        lines.append("In-Reply-To: " + m["in_reply_to"])
    lines.append("Unread:      " + {True: "yes", False: "no", None: "unknown"}[m["unread"]])
    if m["attachments"]:
        lines.append("Attachments:")
        for a in m["attachments"]:
            lines.append("  - %s (%s, %d bytes)" % (a["filename"] or "(unnamed)", a["content_type"], a["size"]))
    lines += ["", m["body"]]
    for a in m["attachments"]:
        if "text" in a:
            lines += ["", "----- attachment: %s -----" % (a["filename"] or a["content_type"]), a["text"].strip()]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_profiles(args):
    profiles = list_profiles()
    if args.json:
        return emit(profiles, True)
    if not profiles:
        return emit("No Thunderbird profiles found. Use --profile-dir PATH.", False)
    out = []
    for p in profiles:
        tags = [t for t in ("active", "default") if p[t]]
        if not p["exists"]:
            tags.append("missing")
        out.append("%s%s\n  %s" % (p["name"], " (%s)" % ", ".join(tags) if tags else "", p["path"]))
    emit("\n".join(out), False)


def cmd_folders(args):
    profile = resolve_profile(args)
    folders = select_folders(all_folders(profile), args.folder, include_trash=True)
    rows = []
    for f in folders:
        count = unread = 0
        if args.count:
            for ref, raw in iter_folder(f):
                s = summarize(ref, raw, f)
                if s["deleted"]:
                    continue
                count += 1
                unread += 1 if s["unread"] else 0
        row = {"path": f["path"], "kind": f["kind"], "trash": f["trash"], "sent": f["sent"], "inbox": f["inbox"]}
        if args.count:
            row.update(messages=count, unread=unread)
        rows.append(row)
    if args.json:
        return emit(rows, True)
    out = ["Profile: " + profile]
    for r in rows:
        tags = [t for t in ("inbox", "sent", "trash") if r[t]]
        extra = "  (%d messages, %d unread)" % (r["messages"], r["unread"]) if args.count else ""
        out.append("  %s%s%s" % (r["path"], " [%s]" % ",".join(tags) if tags else "", extra))
    emit("\n".join(out), False)


def _emit_list(results, args):
    if args.json:
        return emit(results, True)
    if not results:
        return emit("No messages found.", False)
    emit("\n\n".join(fmt_summary(s) for s in results), False)


def cmd_list(args):
    profile = resolve_profile(args)
    folders = all_folders(profile)
    only = None if args.folder else "inbox"
    _emit_list(run_search(folders, args, only=only), args)


def cmd_search(args):
    profile = resolve_profile(args)
    if args.index:
        return _emit_list(search_index(profile, args), args)
    _emit_list(run_search(all_folders(profile), args), args)


def cmd_show(args):
    profile = resolve_profile(args)
    folders = all_folders(profile)
    folder, ref, raw = resolve_message(folders, args.ref, args.include_trash)
    if raw is None:
        raise SystemExit("error: message not found: %s" % args.ref)
    m = full_message(ref, raw, folder)
    emit(m if args.json else fmt_full(m), args.json)


def cmd_thread(args):
    profile = resolve_profile(args)
    msgs = build_thread(all_folders(profile), args.ref, args.include_trash)
    if args.json:
        return emit(msgs, True)
    sep = "\n\n" + "=" * 72 + "\n\n"
    emit(sep.join(fmt_full(m) for m in msgs), False)


def cmd_sent_to(args):
    profile = resolve_profile(args)
    prefs = read_prefs(profile)
    folders = all_folders(profile, prefs)
    mine = own_addresses(prefs)
    ns = argparse.Namespace(**vars(args))
    ns.recipient = args.address
    ns.limit = 0
    candidates = run_search(folders, ns, only="sent")
    if not candidates and mine:
        # No folder recognised as "Sent": fall back to messages sent from own identities.
        candidates = [s for s in run_search(folders, ns)
                      if any(a in s["from"].lower() for a in mine)]
    picked = candidates[: args.limit] if args.limit > 0 else candidates
    msgs = []
    for s in picked:
        f, raw = load_ref(folders, s["ref"])
        msgs.append(full_message(s["ref"], raw, f))
    if args.json:
        return emit(msgs, True)
    if not msgs:
        return emit("No sent messages found%s." % (" to " + args.address if args.address else ""), False)
    sep = "\n\n" + "=" * 72 + "\n\n"
    emit(sep.join(fmt_full(m) for m in msgs), False)


def cmd_identities(args):
    profile = resolve_profile(args)
    prefs = read_prefs(profile)
    ids = {}
    for k, v in prefs.items():
        m = re.match(r"^mail\.identity\.([^.]+)\.(useremail|fullName|organization)$", k)
        if m:
            ids.setdefault(m.group(1), {})[m.group(2)] = v
    rows = [{"email": d.get("useremail", ""), "name": d.get("fullName", ""),
             "organization": d.get("organization", "")} for d in ids.values() if d.get("useremail")]
    if args.json:
        return emit(rows, True)
    emit("\n".join("%s <%s>%s" % (r["name"], r["email"], " - " + r["organization"] if r["organization"] else "")
                   for r in rows) or "No identities found.", False)


def cmd_local_llm(args):
    info = detect_local_llm()
    if args.json:
        info["command"] = claude_command(info["suggested_model"] or "<model>")
        return emit(info, True)
    emit(local_llm_section(info).strip(), False)


def cmd_acknowledge(args):
    path = write_ack_marker()
    emit("Acknowledged. Marker written to %s" % path, False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser():
    p = argparse.ArgumentParser(
        prog="tb.py",
        description="Read-only access to local Thunderbird mail. Never sends, deletes or modifies anything.",
    )
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = p.add_subparsers(dest="command")

    def common(sp, folder=True):
        sp.add_argument("--profile", help="profile name (see `profiles`)")
        sp.add_argument("--profile-dir", help="explicit profile directory (contains prefs.js)")
        sp.add_argument("--json", action="store_true", help="machine-readable output")
        sp.add_argument("--include-trash", action="store_true", help="also look into trash folders")
        if folder:
            sp.add_argument("--folder", help="folder path or substring, e.g. 'INBOX' or 'work/Sent'")

    def filters(sp):
        sp.add_argument("--account", help="account name substring")
        sp.add_argument("--from", dest="sender", help="sender contains")
        sp.add_argument("--to", dest="recipient", help="To/Cc/Bcc contains")
        sp.add_argument("--subject", help="subject contains")
        sp.add_argument("--text", help="subject, body or text attachment contains")
        sp.add_argument("--since", help="YYYY-MM-DD or relative like 7d, 2w, 3m, 1y")
        sp.add_argument("--until", help="YYYY-MM-DD (inclusive)")
        sp.add_argument("--unread", action="store_true", help="only unread messages")
        sp.add_argument("--limit", type=int, default=20, help="max results, 0 = all (default 20)")

    sp = sub.add_parser("profiles", help="list Thunderbird profiles")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_profiles)

    sp = sub.add_parser("identities", help="list the user's own email identities")
    common(sp, folder=False)
    sp.set_defaults(func=cmd_identities)

    sp = sub.add_parser("folders", help="list mail folders")
    common(sp)
    sp.add_argument("--count", action="store_true", help="count messages (slower)")
    sp.set_defaults(func=cmd_folders)

    sp = sub.add_parser("list", help="newest messages (all inboxes unless --folder)")
    common(sp)
    filters(sp)
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("search", help="search messages")
    common(sp)
    filters(sp)
    sp.add_argument("--index", action="store_true",
                    help="use Thunderbird's global search index (read-only) instead of scanning folders")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("show", help="show one message in full")
    common(sp, folder=False)
    sp.add_argument("ref", help="ref from list/search output, or a Message-ID")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("thread", help="show the whole conversation of a message")
    common(sp, folder=False)
    sp.add_argument("ref", help="ref from list/search output, or a Message-ID")
    sp.set_defaults(func=cmd_thread)

    sp = sub.add_parser("sent-to", help="messages the user sent (to an address)")
    common(sp)
    filters(sp)
    sp.add_argument("address", nargs="?", help="recipient address or name; omit for latest sent mail")
    sp.set_defaults(func=cmd_sent_to, limit=5)

    sp = sub.add_parser("acknowledge", help="record that the user accepted the privacy notice")
    sp.set_defaults(func=cmd_acknowledge)

    sp = sub.add_parser("local-llm", help="detect a local Ollama install and print the command to use it")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_local_llm)
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_OK
    install_readonly_guard()
    if args.command not in ("acknowledge", "local-llm") and not is_acknowledged():
        print(privacy_notice())
        return EXIT_NEEDS_ACK
    try:
        args.func(args)
    except ReadOnlyViolation as exc:
        print("error: read-only guard: %s" % exc, file=sys.stderr)
        return EXIT_ERROR
    except BrokenPipeError:
        pass
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
