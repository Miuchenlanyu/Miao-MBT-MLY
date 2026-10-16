#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gamewiki 本地服务 / 数据生成器
- 实时扫描 Yunzai 角色 meta 与 Miao-MBT-MLY 数据仓库，对比“已添加/未添加”
- 提供网页 (index.html) 与 JSON 接口
- 支持“添加角色”= 在数据仓库对应 R 级目录创建 normal-character/<角色名>/ 文件夹

用法：
  python server.py            启动本地服务 (默认 http://127.0.0.1:11002)
  python server.py --export   仅生成 data/characters.json 快照后退出（供 file:// 直接打开网页）
  python server.py --port 9000
"""
import os
import json
import shutil
import argparse
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote, quote

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))

GS_ELEM = {"geo": "岩", "pyro": "火", "anemo": "风", "cryo": "冰",
           "electro": "雷", "hydro": "水", "dendro": "草", "multi": "旅行者"}

# 按元素分组（元素直接取自 Yunzai，无需映射）；[图标] 来自 Yunzai 资源
# 绝区零稀有度 S/A -> 星级（用于分组与展示）
ZZZ_RARITY = {"S": 5, "A": 4}
ELEMENT_ORDER = ["岩", "火", "水", "风", "雷", "冰", "草",
                 "物理", "量子", "虚数", "电", "以太", "流明", "其他"]
ELEM_ICON = {
    "gs": {
        "岩": "assets/elem/gs/geo.png", "火": "assets/elem/gs/pyro.png",
        "水": "assets/elem/gs/hydro.png", "风": "assets/elem/gs/anemo.png",
        "雷": "assets/elem/gs/electro.png", "冰": "assets/elem/gs/cryo.png",
        "草": "assets/elem/gs/dendro.png", "旅行者": "assets/elem/gs/multi.png",
    },
    "sr": {
        "雷": "assets/elem/sr/elem-elec.webp", "火": "assets/elem/sr/elem-fire.webp",
        "物理": "assets/elem/sr/elem-phy.webp", "冰": "assets/elem/sr/elm-ice.webp",
        "风": "assets/elem/sr/elem-wind.webp", "量子": "assets/elem/sr/elem-auantum.webp",
        "虚数": "assets/elem/sr/elem-imaginary.webp",
    },
    "zzz": {
        "物理": "assets/elem/zzz/Physical.png", "火": "assets/elem/zzz/Fire.png",
        "冰": "assets/elem/zzz/Ice.png", "电": "assets/elem/zzz/Electric.png",
        "风": "assets/elem/zzz/Wind.png", "以太": "assets/elem/zzz/Ether.png",
        "流明": "assets/elem/zzz/Lumiflux.png",
    },
}


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}





def load_zzz_db():
    """绝区零角色库：ZZZ-Plugin 的 PartnerId2Data.json + ElementData.json（元素码 -> 中文）"""
    cfg = CONFIG.get("zzz_db") or {}
    pj, ej = cfg.get("partner"), cfg.get("element")
    if not pj or not os.path.isfile(pj):
        return {}, {}
    try:
        partners = json.load(open(pj, encoding="utf-8"))
    except Exception:
        return {}, {}
    emap = {}
    if ej and os.path.isfile(ej):
        try:
            for e in json.load(open(ej, encoding="utf-8")):
                if isinstance(e, dict) and (e.get("sub_element_type") in (0, None)):
                    emap[str(e.get("element_type"))] = e.get("zh")
        except Exception:
            pass
    return partners, emap


def scan_game(g):
    cfg = CONFIG["games"][g]
    data_dir = os.path.join(CONFIG["data_repo"], cfg["dir"])
    chars = []
    if g == "zzz":
        # 绝区零：miao-plugin 无 meta，改用 ZZZ-Plugin 的角色库
        partners, emap = load_zzz_db()
        for v in partners.values():
            if not isinstance(v, dict):
                continue
            cname = v.get("name")
            rarity = (v.get("Rarity") or "").strip()
            if not cname or not rarity:
                continue  # 跳过无稀有度的条目（哲/铃 等非可操作角色）
            full = v.get("full_name") or ""
            if not _safe_name(full):
                full = ""  # 丢弃 '...' 之类占位全名（如克拉蕾/洛克茜的数据）
            avatar = f"assets/avatars/zzz/{cname}.png"
            if not os.path.isfile(os.path.join(HERE, avatar)):
                avatar = ""
            added = False
            for lvl in CONFIG["r_levels"]:
                for nm in (cname, full):
                    if nm and os.path.isdir(os.path.join(data_dir, lvl, "normal-character", nm)):
                        added = True
                        break
                if added:
                    break
            chars.append({"name": cname, "star": ZZZ_RARITY.get(rarity, 0),
                          "elem": emap.get(str(v.get("ElementType")), "") or "其他",
                          "camp": v.get("Camp") or "",
                          "levels": level_status(data_dir, [cname, full]),
                          "added": added, "avatar": avatar})
        if not chars:
            return {"label": cfg["label"], "status": "pending",
                    "note": "未找到 ZZZ 角色库，请在 config.json 的 zzz_db 中配置 PartnerId2Data.json 路径。",
                    "elements": {}, "elemIcons": {}, "total": 0, "added": 0, "missing": 0, "extra": 0}
    else:
        meta = cfg.get("meta")
        if not meta:
            return {"label": cfg["label"], "status": "pending",
                    "note": "数据源待接入：Yunzai 暂无该游戏角色 meta，后续接入后自动显示。",
                    "elements": {}, "elemIcons": {}, "total": 0, "added": 0, "missing": 0, "extra": 0}
        meta_dir = os.path.join(CONFIG["yunai_meta"], meta, "character")
        if os.path.isdir(meta_dir):
            for name in sorted(os.listdir(meta_dir)):
                dj = os.path.join(meta_dir, name, "data.json")
                if not os.path.isfile(dj):
                    continue
                try:
                    d = json.load(open(dj, encoding="utf-8"))
                except Exception:
                    continue
                cname = d.get("name") or name
                star = d.get("star")
                elem = d.get("elem")
                elem_label = GS_ELEM.get(elem, elem) if g == "gs" else elem
                added = False
                for lvl in CONFIG["r_levels"]:
                    if os.path.isdir(os.path.join(data_dir, lvl, "normal-character", cname)):
                        added = True
                        break
                avatar = f"assets/avatars/{g}/{cname}.webp"
                if not os.path.isfile(os.path.join(HERE, avatar)):
                    avatar = ""
                chars.append({"name": cname, "star": star, "elem": elem_label,
                              "levels": level_status(data_dir, [cname]),
                              "added": added, "avatar": avatar})

    elements = {}
    elem_icons = {}
    for c in chars:
        el = c["elem"] or "其他"
        elements.setdefault(el, {}).setdefault(str(c["star"]), []).append(c)
        elem_icons[el] = ELEM_ICON.get(g, {}).get(el, "")
    # 排序：元素按预定义顺序，未知排后；星级降序；角色按名
    ordered = {}
    for el in ELEMENT_ORDER:
        if el in elements:
            ordered[el] = elements[el]
    for el in sorted(elements.keys()):
        if el not in ordered:
            ordered[el] = elements[el]
    for el, stars in ordered.items():
        for s in list(stars.keys()):
            stars[s] = sorted(stars[s], key=lambda x: x["name"])
        stars = {k: stars[k] for k in sorted(stars.keys(), key=lambda x: -int(x))}
        ordered[el] = stars

    total = len(chars)
    added_c = sum(1 for c in chars if c["added"])
    return {"label": cfg["label"], "status": "ok", "elements": ordered, "elemIcons": elem_icons,
            "total": total, "added": added_c, "missing": total - added_c, "extra": 0}


def build_data():
    return {"generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "games": {g: scan_game(g) for g in CONFIG["games"]}}


def copy_avatars():
    """把 Yunzai 角色大头照 (meta-*/character/<名>/imgs/face.webp) 复制到 assets/avatars/<游戏>/"""
    dst_root = os.path.join(HERE, "assets", "avatars")
    copied = 0
    for g, cfg in CONFIG["games"].items():
        meta = cfg.get("meta")
        if not meta:
            continue
        meta_dir = os.path.join(CONFIG["yunai_meta"], meta, "character")
        out_dir = os.path.join(dst_root, g)
        os.makedirs(out_dir, exist_ok=True)
        if not os.path.isdir(meta_dir):
            continue
        for name in os.listdir(meta_dir):
            src = os.path.join(meta_dir, name, "imgs", "face.webp")
            if not os.path.isfile(src):
                continue
            dst = os.path.join(out_dir, f"{name}.webp")
            try:
                shutil.copyfile(src, dst)
                copied += 1
            except Exception:
                pass
    print(f"[ok] 已复制大头照 {copied} 张到 assets/avatars/")


def copy_elem_icons():
    """把 Yunzai 的元素图标复制到 assets/elem/<游戏>/"""
    dst_root = os.path.join(HERE, "assets", "elem")
    os.makedirs(dst_root, exist_ok=True)
    yunzai_plugins = os.path.dirname(os.path.dirname(CONFIG["yunai_meta"]))  # .../Yunzai/plugins
    sources = {
        "gs": (os.path.join(yunzai_plugins, "genshin", "resources", "img", "element"),
               ["geo.png", "pyro.png", "hydro.png", "anemo.png",
                "electro.png", "cryo.png", "dendro.png", "multi.png"]),
        "sr": (os.path.join(CONFIG["yunai_meta"], "meta-sr", "public", "icons"),
               ["elem-elec.webp", "elem-fire.webp", "elem-phy.webp", "elm-ice.webp",
                "elem-wind.webp", "elem-auantum.webp", "elem-imaginary.webp"]),
        "zzz": (os.path.join(os.path.dirname(os.path.dirname(CONFIG.get("zzz_db", {}).get("partner", ""))),
                             "common", "images", "element"),
                ["Physical.png", "Fire.png", "Ice.png", "Electric.png",
                 "Wind.png", "Ether.png", "Lumiflux.png"]),
    }
    copied = 0
    for g, (src_dir, files) in sources.items():
        out_dir = os.path.join(dst_root, g)
        os.makedirs(out_dir, exist_ok=True)
        if not os.path.isdir(src_dir):
            continue
        for fn in files:
            src = os.path.join(src_dir, fn)
            if not os.path.isfile(src):
                continue
            try:
                shutil.copyfile(src, os.path.join(out_dir, fn))
                copied += 1
            except Exception:
                pass
    print(f"[ok] 已复制元素图标 {copied} 张到 assets/elem/")


IMG_EXT = (".webp", ".png", ".jpg", ".jpeg", ".gif")


def repo_images(g, name):
    """列出数据仓库里某角色已有的图片（按 R/R17/R18 分级）"""
    cfg = CONFIG["games"].get(g)
    if not cfg or not name:
        return []
    data_dir = os.path.join(CONFIG["data_repo"], cfg["dir"])
    out = []
    for lvl in CONFIG["r_levels"]:
        d = os.path.join(data_dir, lvl, "normal-character", name)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not os.path.isfile(os.path.join(d, fn)):
                continue
            if os.path.splitext(fn)[1].lower() not in IMG_EXT:
                continue
            out.append({"level": lvl, "file": fn,
                        "url": f"/repo-img?g={g}&l={quote(lvl)}&n={quote(name)}&f={quote(fn)}"})
    return out


def copy_zzz_avatars():
    """绝区零大头照：role_circle/IconRoleCircle<sprite_id>.png -> assets/avatars/zzz/<角色名>.png"""
    cfg = CONFIG.get("zzz_db") or {}
    src_dir = cfg.get("avatar_dir")
    pattern = cfg.get("avatar_pattern") or "IconRoleCircle{sprite_id}.png"
    if not src_dir or not os.path.isdir(src_dir):
        return 0
    partners, _ = load_zzz_db()
    out_dir = os.path.join(HERE, "assets", "avatars", "zzz")
    os.makedirs(out_dir, exist_ok=True)
    copied = 0
    for v in partners.values():
        if not isinstance(v, dict):
            continue
        cname = v.get("name")
        sid = str(v.get("sprite_id") or "")
        if not cname or not sid or not (v.get("Rarity") or "").strip():
            continue
        src = os.path.join(src_dir, pattern.format(sprite_id=sid))
        if not os.path.isfile(src):
            continue
        try:
            shutil.copyfile(src, os.path.join(out_dir, f"{cname}.png"))
            copied += 1
        except Exception:
            pass
    return copied


def _safe_name(nm):
    """过滤 '...' 之类占位名——Windows 会把它们当路径解析（normal-character\\...）"""
    return bool(nm) and nm.strip(". ") == nm and nm not in (".", "..")


def level_status(data_dir, names):
    """统计各分级目录（R/R17/R18）下该角色的图片数量，供前端网格显示"""
    out = {}
    for lvl in CONFIG["r_levels"]:
        cnt = 0
        for nm in names:
            if not _safe_name(nm):
                continue
            d = os.path.join(data_dir, lvl, "normal-character", nm)
            if not os.path.isdir(d):
                continue
            try:
                entries = os.listdir(d)
            except OSError:
                continue
            for fn in entries:
                fp = os.path.join(d, fn)
                if os.path.isfile(fp) and os.path.splitext(fn)[1].lower() in IMG_EXT:
                    cnt += 1
        out[lvl] = cnt
    return out


def add_character(g, name, rlevel):
    cfg = CONFIG["games"].get(g)
    if not cfg:
        return {"ok": False, "error": f"未知游戏 {g}"}
    if rlevel not in CONFIG["r_levels"]:
        rlevel = "R"
    target = os.path.join(CONFIG["data_repo"], cfg["dir"], rlevel, "normal-character", name)
    os.makedirs(target, exist_ok=True)
    marker = os.path.join(target, "added.json")
    info = {"name": name, "game": g, "rlevel": rlevel,
            "addedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "Gamewiki"}
    try:
        with open(marker, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return {"ok": True, "path": target}


def export_snapshot():
    copy_avatars()
    n = copy_zzz_avatars()
    if n:
        print(f"[ok] 已复制绝区零大头照 {n} 张到 assets/avatars/zzz/")
    copy_elem_icons()
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    out = os.path.join(HERE, "data", "characters.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(build_data(), f, ensure_ascii=False, indent=2)
    print(f"[ok] 已生成快照: {out}")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = urlparse(self.path)
        if p.path in ("/", "/index.html"):
            self._serve_file("index.html", "text/html; charset=utf-8")
        elif p.path == "/api/data":
            self._send(200, json.dumps(build_data(), ensure_ascii=False))
        elif p.path == "/api/config":
            self._send(200, json.dumps({"games": CONFIG["games"],
                                        "rLevels": CONFIG["r_levels"]}, ensure_ascii=False))
        elif p.path == "/api/imgs":
            q = parse_qs(p.query)
            g = (q.get("game") or [""])[0]
            name = (q.get("name") or [""])[0]
            if g not in CONFIG["games"] or not name:
                self._send(400, json.dumps({"error": "bad params"}, ensure_ascii=False))
                return
            self._send(200, json.dumps({"name": name, "images": repo_images(g, name)},
                                       ensure_ascii=False))
        elif p.path == "/api/sync":
            # 给插件(11001)用的清单：各角色 + R/R17/R18 各级图片数量
            q = parse_qs(p.query)
            want = (q.get("game") or [""])[0]
            games = {}
            for g, cfg in CONFIG["games"].items():
                if want and want != g:
                    continue
                info = scan_game(g)
                if info.get("status") != "ok":
                    continue
                chars = []
                for stars in info["elements"].values():
                    for lst in stars.values():
                        for c in lst:
                            chars.append({"name": c["name"], "star": c["star"],
                                          "elem": c["elem"], "levels": c.get("levels", {})})
                games[g] = {"label": cfg["label"], "dir": cfg["dir"], "chars": chars}
            self._send(200, json.dumps(
                {"generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "rLevels": CONFIG["r_levels"], "games": games}, ensure_ascii=False))
        elif p.path == "/api/sync/files":
            # 某角色某分级下的具体文件名与大小（供插件增量下载）
            q = parse_qs(p.query)
            g = (q.get("game") or [""])[0]
            name = (q.get("name") or [""])[0]
            lvl = (q.get("level") or [""])[0]
            cfg = CONFIG["games"].get(g)
            if not cfg or not name or lvl not in CONFIG["r_levels"]:
                self._send(400, json.dumps({"error": "bad params"}, ensure_ascii=False))
                return
            d = os.path.join(CONFIG["data_repo"], cfg["dir"], lvl, "normal-character", name)
            files = []
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d)):
                    fp = os.path.join(d, fn)
                    if os.path.isfile(fp) and os.path.splitext(fn)[1].lower() in IMG_EXT:
                        files.append({"f": fn, "size": os.path.getsize(fp)})
            self._send(200, json.dumps({"files": files}, ensure_ascii=False))
        elif p.path == "/repo-img":
            q = parse_qs(p.query)
            g = (q.get("g") or [""])[0]
            lvl = (q.get("l") or [""])[0]
            name = (q.get("n") or [""])[0]
            fn = (q.get("f") or [""])[0]
            cfg = CONFIG["games"].get(g)
            if (not cfg or lvl not in CONFIG["r_levels"] or not name or not fn
                    or os.path.basename(fn) != fn or os.path.basename(name) != name):
                self._send(404, json.dumps({"error": "not found"}))
                return
            base = os.path.normpath(os.path.join(CONFIG["data_repo"], cfg["dir"],
                                                 lvl, "normal-character"))
            fp = os.path.normpath(os.path.join(base, name, fn))
            if not fp.startswith(base + os.sep) or not os.path.isfile(fp):
                self._send(404, json.dumps({"error": "not found"}))
                return
            ext = os.path.splitext(fp)[1].lower()
            mime = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg", ".gif": "image/gif"}.get(ext, "application/octet-stream")
            try:
                with open(fp, "rb") as f:
                    self._send(200, f.read(), mime)
            except Exception:
                self._send(500, json.dumps({"error": "read fail"}))
        elif p.path.startswith("/static/") or p.path in ("/app.js", "/style.css"):
            fn = p.path.split("/")[-1]
            self._serve_file(fn, "application/javascript; charset=utf-8"
                             if fn.endswith(".js") else "text/css; charset=utf-8")
        elif p.path.startswith("/assets/"):
            rel = unquote(p.path.lstrip("/"))
            fp = os.path.normpath(os.path.join(HERE, rel))
            assets_base = os.path.join(HERE, "assets") + os.sep
            if not fp.startswith(assets_base) or not os.path.isfile(fp):
                self._send(404, json.dumps({"error": "not found"}))
                return
            ext = os.path.splitext(fp)[1].lower()
            mime = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg", ".gif": "image/gif"}.get(ext, "application/octet-stream")
            try:
                with open(fp, "rb") as f:
                    self._send(200, f.read(), mime)
            except Exception:
                self._send(500, json.dumps({"error": "read fail"}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        p = urlparse(self.path)
        if p.path == "/api/add":
            try:
                ln = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(ln).decode("utf-8")
                body = json.loads(raw)
            except Exception as e:
                self._send(400, json.dumps({"ok": False, "error": str(e)}))
                return
            g = body.get("game")
            name = (body.get("name") or "").strip()
            rlevel = body.get("rlevel", "R")
            if not name:
                self._send(400, json.dumps({"ok": False, "error": "缺少角色名"}))
                return
            res = add_character(g, name, rlevel)
            if res.get("ok"):
                export_snapshot()  # 添加后刷新快照
            self._send(200 if res.get("ok") else 500, json.dumps(res, ensure_ascii=False))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def _serve_file(self, fn, ctype):
        fp = os.path.join(HERE, fn)
        if not os.path.isfile(fp):
            self._send(404, json.dumps({"error": f"missing {fn}"}))
            return
        with open(fp, "rb") as f:
            self._send(200, f.read(), ctype)

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=11002)
    ap.add_argument("--host", default="0.0.0.0", help="监听地址，默认 0.0.0.0（允许局域网访问）")
    ap.add_argument("--export", action="store_true", help="仅导出快照后退出")
    args = ap.parse_args()
    if args.export:
        export_snapshot()
        return
    export_snapshot()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[ok] Gamewiki 服务已启动: http://{args.host}:{args.port}")
    print("     按 Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
        print("\n[stop] 已停止")


if __name__ == "__main__":
    main()
