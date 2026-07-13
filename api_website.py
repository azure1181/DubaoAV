from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import socket
import sys
import threading
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:
    import pandas as pd
except ImportError as exc:
    raise SystemExit(
        "Thieu thu vien pandas/openpyxl. Cai bang lenh: python -m pip install pandas openpyxl"
    ) from exc


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web_report"
OUTPUT_DIR = ROOT / "output_forecast"
STATIC_DATA_FILE = WEB_ROOT / "forecast-data.json"
STATIC_DATA_JS_FILE = WEB_ROOT / "forecast-data.js"
DEFAULT_PORT = 8000

YEAR_OUTPUTS = {
    2026: ROOT / "output_forecast",
    2027: ROOT / "Output_2027",
}

_payload_cache: dict[int, tuple[tuple[tuple[str, int, int], ...], dict]] = {}
_payload_cache_lock = threading.RLock()


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def available_years() -> list[int]:
    return sorted(year for year in YEAR_OUTPUTS if report_file_for_year(year).exists())


def default_year() -> int:
    years = available_years()
    return years[-1] if years else 2026


def output_dir_for_year(year: int) -> Path:
    return YEAR_OUTPUTS.get(year, ROOT / f"Output_{year}")


def report_file_for_year(year: int) -> Path:
    return output_dir_for_year(year) / f"bao_cao_du_bao_{year}.xlsx"


def chart_file_for_year(year: int) -> Path:
    return output_dir_for_year(year) / f"du_bao_nuoc_ve_{year}.png"


def comment_file_for_year(year: int) -> Path:
    return output_dir_for_year(year) / f"nhan_xet_du_bao_{year}.txt"


def public_files_for_year(year: int) -> dict[str, Path]:
    return {
        f"bao_cao_du_bao_{year}.xlsx": report_file_for_year(year),
        f"du_bao_nuoc_ve_{year}.png": chart_file_for_year(year),
        f"nhan_xet_du_bao_{year}.txt": comment_file_for_year(year),
    }


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def number_or_none(value: object) -> float | int | None:
    if pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value.item() if hasattr(value, "item") else value


def clean_records(df: pd.DataFrame) -> list[dict]:
    records = []
    for row in df.to_dict(orient="records"):
        records.append({key: number_or_none(value) for key, value in row.items()})
    return records


def normalize_year(raw_year: str | None) -> int:
    if not raw_year:
        return default_year()
    try:
        year = int(raw_year)
    except ValueError as exc:
        raise ValueError(f"Nam du bao khong hop le: {raw_year}") from exc
    if year < 1900 or year > 2100:
        raise ValueError(f"Nam du bao nam ngoai pham vi cho phep: {year}")
    return year


def _payload_signature(year: int) -> tuple[tuple[str, int, int], ...]:
    signature = []
    for path in (report_file_for_year(year), chart_file_for_year(year), comment_file_for_year(year)):
        if path.exists():
            stat = path.stat()
            signature.append((str(path), stat.st_mtime_ns, stat.st_size))
        else:
            signature.append((str(path), 0, 0))
    return tuple(signature)


def read_report_payload(year: int = 2026) -> dict:
    report_file = report_file_for_year(year)
    chart_file = chart_file_for_year(year)
    comment_file = comment_file_for_year(year)

    if not report_file.exists():
        raise FileNotFoundError(f"Khong tim thay file bao cao: {report_file}")

    signature = _payload_signature(year)
    with _payload_cache_lock:
        cached = _payload_cache.get(year)
        if cached and cached[0] == signature:
            return cached[1]

    monthly = pd.read_excel(report_file, sheet_name="Tong_hop")
    annual = pd.read_excel(report_file, sheet_name="Tong_hop_nam")
    calc = pd.read_excel(report_file, sheet_name="Chi_tieu_tinh_toan")
    historical_monthly = pd.read_excel(report_file, sheet_name="Lich_su_1977_2025")

    comment = comment_file.read_text(encoding="utf-8") if comment_file.exists() else ""
    forecast_mean = float(monthly["forecast_flow_m3s"].mean())
    history_mean = float(monthly["historical_mean_m3s"].mean())
    ratio = forecast_mean / history_mean if history_mean else None
    peak = monthly.loc[monthly["forecast_flow_m3s"].idxmax()]
    low = monthly.loc[monthly["forecast_flow_m3s"].idxmin()]

    if ratio is None:
        scenario = "Chưa xác định"
    elif ratio < 0.90:
        scenario = "Khô hơn trung bình lịch sử"
    elif ratio > 1.10:
        scenario = "Nhiều nước hơn trung bình lịch sử"
    else:
        scenario = "Xấp xỉ trung bình lịch sử"

    payload = {
        "year": year,
        "generated_at": datetime.fromtimestamp(report_file.stat().st_mtime).isoformat(timespec="seconds"),
        "report_file": report_file.name,
        "chart_file": chart_file.name if chart_file.exists() else None,
        "executive_comment": comment,
        "summary": {
            "forecast_mean_m3s": round(forecast_mean, 2),
            "historical_mean_m3s": round(history_mean, 2),
            "ratio_vs_history": round(ratio, 4) if ratio is not None else None,
            "scenario": scenario,
            "peak_month": int(peak["month"]),
            "peak_flow_m3s": round(float(peak["forecast_flow_m3s"]), 2),
            "low_month": int(low["month"]),
            "low_flow_m3s": round(float(low["forecast_flow_m3s"]), 2),
        },
        "monthly": clean_records(monthly),
        "annual": clean_records(annual),
        "historical_monthly": clean_records(historical_monthly),
        "calculation": clean_records(calc),
        "downloads": {
            "excel": f"/download/{year}/bao_cao_du_bao_{year}.xlsx",
            "chart": f"/download/{year}/du_bao_nuoc_ve_{year}.png",
            "comment": f"/download/{year}/nhan_xet_du_bao_{year}.txt",
        },
    }

    with _payload_cache_lock:
        _payload_cache[year] = (signature, payload)
    return payload


def api_index(base_url: str) -> dict:
    years = available_years()
    endpoints = {
        "all_forecasts": "/api/forecast/all",
        "forecast_by_year": "/api/forecast?year=2027",
        "summary": "/api/summary?year=2027",
        "monthly": "/api/monthly?year=2027",
        "annual": "/api/annual?year=2027",
        "historical_monthly": "/api/historical?year=2027",
        "calculation": "/api/calculation?year=2027",
        "files": "/api/files?year=2027",
        "chart": "/chart.png?year=2027",
        "website": "/index.html",
    }
    return {
        "name": "Forecast Water Report API",
        "version": "2.0",
        "base_url": base_url,
        "available_years": years,
        "default_year": default_year(),
        "endpoints": {name: base_url + path for name, path in endpoints.items()},
        "note": "Them tham so ?year=2026 hoac ?year=2027 de chon nam bao cao.",
    }


def local_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


def export_static_payload() -> Path:
    WEB_ROOT.mkdir(exist_ok=True)
    payloads = {}
    for year in sorted(YEAR_OUTPUTS):
        try:
            payloads[str(year)] = read_report_payload(year)
        except FileNotFoundError:
            continue

    STATIC_DATA_FILE.write_text(json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8")
    STATIC_DATA_JS_FILE.write_text(
        "window.FORECAST_DATA_BY_YEAR = "
        + json.dumps(payloads, ensure_ascii=False, indent=2)
        + ";\nwindow.FORECAST_DATA = window.FORECAST_DATA_BY_YEAR['2026'] || Object.values(window.FORECAST_DATA_BY_YEAR)[0];\n",
        encoding="utf-8",
    )
    return STATIC_DATA_FILE


class ForecastHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64


class ForecastHandler(SimpleHTTPRequestHandler):
    server_version = "ForecastAPI/2.0"
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, format: str, *args: object) -> None:
        if getattr(self.server, "verbose", True):
            super().log_message(format, *args)

    def request_base_url(self) -> str:
        public_url = getattr(self.server, "public_url", None)
        if public_url:
            return public_url.rstrip("/")

        scheme = "http"
        host = self.headers.get("Host", f"127.0.0.1:{self.server.server_port}")
        if getattr(self.server, "trust_proxy", False):
            scheme = self.headers.get("X-Forwarded-Proto", scheme).split(",", 1)[0].strip()
            host = self.headers.get("X-Forwarded-Host", host).split(",", 1)[0].strip()
        return f"{scheme}://{host}"

    def end_headers(self) -> None:
        origin = self.headers.get("Origin")
        allowed = getattr(self.server, "cors_origins", {"*"})
        if "*" in allowed:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin and origin in allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "same-origin")
        super().end_headers()

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_file(self, path: Path, *, download: bool = False) -> None:
        if not path.exists() or not path.is_file():
            self.send_json({"error": f"Khong tim thay file: {path.name}"}, status=404)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        stat = path.stat()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(stat.st_size))
        self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
        self.send_header("Cache-Control", "public, max-age=300")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        if self.command != "HEAD":
            with path.open("rb") as source:
                shutil.copyfileobj(source, self.wfile, length=256 * 1024)

    def send_public_report_file(self, year: int, file_name: str) -> None:
        allowed_files = public_files_for_year(year)
        path = allowed_files.get(file_name)
        if path is None:
            self.send_json({"error": "File khong nam trong danh sach duoc chia se"}, status=404)
            return
        self.send_file(path, download=True)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Accept, Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        try:
            if len(self.path) > 4096:
                self.send_json({"error": "URL qua dai"}, status=414)
                return
            parsed = urlparse(self.path)
            route = unquote(parsed.path)
            params = parse_qs(parsed.query)
            year = normalize_year(params.get("year", [None])[0])

            if route == "/healthz":
                self.send_json({"status": "ok", "available_years": available_years()})
                return
            if route == "/api":
                self.send_json(api_index(self.request_base_url()))
                return
            if route == "/api/years":
                self.send_json({"years": available_years()})
                return
            if route == "/api/forecast":
                self.send_json(read_report_payload(year))
                return
            if route == "/api/forecast/all":
                payloads = {str(item): read_report_payload(item) for item in available_years()}
                self.send_json({"years": available_years(), "reports": payloads})
                return
            if route == "/api/summary":
                payload = read_report_payload(year)
                self.send_json(
                    {
                        "year": year,
                        "generated_at": payload["generated_at"],
                        "summary": payload["summary"],
                        "executive_comment": payload["executive_comment"],
                    }
                )
                return
            if route == "/api/monthly":
                self.send_json({"year": year, "monthly": read_report_payload(year)["monthly"]})
                return
            if route == "/api/annual":
                self.send_json({"year": year, "annual": read_report_payload(year)["annual"]})
                return
            if route == "/api/historical":
                self.send_json({"year": year, "historical_monthly": read_report_payload(year)["historical_monthly"]})
                return
            if route == "/api/calculation":
                self.send_json({"year": year, "calculation": read_report_payload(year)["calculation"]})
                return
            if route == "/api/files":
                files = []
                for file_name, path in public_files_for_year(year).items():
                    files.append(
                        {
                            "name": file_name,
                            "exists": path.exists(),
                            "size_bytes": path.stat().st_size if path.exists() else None,
                            "url": f"/download/{year}/{file_name}",
                        }
                    )
                self.send_json({"year": year, "files": files})
                return
            if route == "/chart.png":
                self.send_file(chart_file_for_year(year))
                return
            if route.startswith("/download/"):
                parts = [part for part in route.split("/") if part]
                if len(parts) >= 3 and parts[1].isdigit():
                    download_year = int(parts[1])
                    file_name = parts[2]
                else:
                    download_year = year
                    file_name = Path(route).name
                self.send_public_report_file(download_year, file_name)
                return
            if route in {"/", "/index.html"}:
                self.send_file(WEB_ROOT / "index.html")
                return

            static_path = (WEB_ROOT / route.lstrip("/")).resolve()
            if static_path == WEB_ROOT.resolve() or WEB_ROOT.resolve() in static_path.parents:
                self.send_file(static_path)
                return

            self.send_json({"error": "Khong tim thay endpoint"}, status=404)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
        except FileNotFoundError as exc:
            self.send_json({"error": str(exc)}, status=404)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            if getattr(self.server, "verbose", True):
                self.log_error("Unhandled error: %s", exc)
            self.send_json({"error": str(exc)}, status=500)


def main() -> None:
    configure_console()
    env_port = os.getenv("PORT")
    try:
        default_port_from_env = int(env_port) if env_port else None
    except ValueError as exc:
        raise SystemExit(f"Bien moi truong PORT khong hop le: {env_port}") from exc

    parser = argparse.ArgumentParser(description="API website cho bao cao du bao nuoc ve.")
    parser.add_argument("port_pos", nargs="?", type=int, help="Cong chay API, vi du: 8000")
    parser.add_argument("--port", type=int, default=default_port_from_env, help="Cong chay API, vi du: 8000")
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="Dia chi bind API; mac dinh chia se tren LAN.",
    )
    parser.add_argument(
        "--public-url",
        default=os.getenv("PUBLIC_URL"),
        help="URL cong khai HTTPS, vi du https://forecast.example.vn",
    )
    parser.add_argument(
        "--trust-proxy",
        action="store_true",
        default=env_flag("TRUST_PROXY"),
        help="Tin X-Forwarded-* tu reverse proxy/tunnel.",
    )
    parser.add_argument(
        "--cors-origin",
        default=os.getenv("CORS_ORIGIN", "*"),
        help="Origin duoc goi API, phan cach bang dau phay. Mac dinh: *",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=env_flag("QUIET"),
        help="Tat access log cho tung request.",
    )
    parser.add_argument("--export-json", action="store_true", help="Xuat du lieu tinh cho web_report")
    args = parser.parse_args()

    if args.export_json:
        path = export_static_payload()
        print(f"Da xuat du lieu tinh: {path}")
        return

    port = args.port or args.port_pos or DEFAULT_PORT
    if not 1 <= port <= 65535:
        parser.error("Cong phai nam trong khoang 1-65535")

    if not WEB_ROOT.exists():
        raise SystemExit(f"Khong tim thay thu muc giao dien: {WEB_ROOT}")

    server = ForecastHTTPServer((args.host, port), ForecastHandler)
    server.public_url = args.public_url
    server.trust_proxy = args.trust_proxy
    server.cors_origins = {item.strip() for item in args.cors_origin.split(",") if item.strip()}
    server.verbose = not args.quiet
    display_host = "127.0.0.1" if args.host in {"0.0.0.0", ""} else args.host
    print(f"API website dang chay tai: http://{display_host}:{port}")
    if args.host in {"0.0.0.0", ""}:
        for address in local_ipv4_addresses():
            print(f"Chia se LAN: http://{address}:{port}/")
    if args.public_url:
        print(f"Internet: {args.public_url.rstrip('/')}/")
    print("Kiem tra: /healthz | Danh muc API: /api | Website: /")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nDang dung API...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
