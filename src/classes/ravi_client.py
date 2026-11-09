"""Client helpers for the Ravi API caption service."""

import json
import os
import tempfile
import threading
import time
from urllib.parse import urljoin, urlparse

import requests

from classes import http_client
from classes.logger import log

DEFAULT_TIMEOUT = (3.0, 8.0)


class RaviClient:
    """Small HTTP client for the independent Ravi API integration."""

    def __init__(self, base_url):
        self.base_url = self.normalize_base_url(base_url)

    @staticmethod
    def normalize_base_url(url):
        text = str(url or "").strip()
        if not text:
            return ""
        if not text.startswith(("http://", "https://")):
            text = "https://" + text
        return text.rstrip("/")

    def _resolve_url(self, path):
        if not self.base_url:
            raise ValueError("Ravi API URL is not configured.")
        if not path:
            return self.base_url
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def ping(self, timeout=DEFAULT_TIMEOUT):
        response = requests.get(
            self._resolve_url("/api/v1/health/"),
            timeout=timeout,
            verify=http_client.verify_path(),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Invalid health response from Ravi API")
        status = str(payload.get("status", "")).lower()
        service = str(payload.get("service", "")).lower()
        if status != "ok" or service != "ravi-api":
            raise ValueError("Unexpected Ravi API health response: {}".format(payload))
        return payload

    def create_caption_job(self, audio_path, language="en", words_per_caption=4, max_line_chars=24, timeout=DEFAULT_TIMEOUT):
        if not audio_path or not os.path.exists(audio_path):
            raise ValueError("Audio file is missing for caption request")

        with open(audio_path, "rb") as handle:
            response = requests.post(
                self._resolve_url("/api/v1/captions/jobs"),
                files={"audio": (os.path.basename(audio_path), handle, "audio/wav")},
                data={
                    "language": language,
                    "words_per_caption": int(words_per_caption),
                    "max_line_chars": int(max_line_chars),
                },
                timeout=timeout,
                verify=http_client.verify_path(),
            )
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Invalid job creation response from Ravi API")
        job_id = payload.get("job_id")
        if not job_id:
            raise ValueError("Ravi API response did not include a job_id")
        return payload

    def get_job(self, job_id, timeout=DEFAULT_TIMEOUT):
        response = requests.get(
            self._resolve_url(f"/api/v1/captions/jobs/{job_id}/"),
            timeout=timeout,
            verify=http_client.verify_path(),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Invalid caption job status from Ravi API")
        return payload

    def download_result(self, job_id, output_path, timeout=DEFAULT_TIMEOUT):
        url = self._resolve_url(f"/api/v1/captions/jobs/{job_id}/result/")
        response = requests.get(
            url,
            timeout=timeout,
            verify=http_client.verify_path(),
        )
        response.raise_for_status()
        with open(output_path, "wb") as handle:
            handle.write(response.content)
        return output_path

    def download_result_text(self, job_id, timeout=DEFAULT_TIMEOUT):
        with tempfile.NamedTemporaryFile(suffix=".vtt", delete=False) as handle:
            temp_path = handle.name
        try:
            self.download_result(job_id, temp_path, timeout=timeout)
            with open(temp_path, "r", encoding="utf-8") as handle:
                return handle.read()
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _first_caption_text(vtt_text):
    lines = [line.strip() for line in str(vtt_text or "").splitlines() if line.strip()]
    for line in lines:
        if line.startswith("WEBVTT"):
            continue
        if "-->" in line:
            continue
        if line.startswith("NOTE"):
            continue
        if not line:
            continue
        return line
    return str(vtt_text or "").strip()


class RaviCaptionService:
    """Generate and attach caption data for a selected timeline clip."""

    def __init__(self, window=None):
        self.window = window

    @staticmethod
    def configured_url():
        try:
            from classes.app import get_app
            app = get_app()
            if app is None:
                return ""
            settings = getattr(app, "get_settings", lambda: None)()
            if settings is None:
                return ""
            return str(settings.get("ravi-api-url") or "").strip().rstrip("/")
        except Exception:
            return ""

    def _status_message(self, text, timeout=3000):
        if self.window and getattr(self.window, "statusBar", None):
            self.window.statusBar.showMessage(text, timeout)

    def _show_error(self, message):
        if self.window:
            from qt_api import QMessageBox
            QMessageBox.warning(self.window, "Ravi API", str(message))
        else:
            log.warning("Ravi API: %s", message)

    def _clip_reader_path(self, clip):
        if clip is None:
            return ""
        if isinstance(clip.data, dict):
            reader = clip.data.get("reader") or {}
            if isinstance(reader, dict):
                path_value = reader.get("path") or reader.get("file_path") or ""
                if path_value:
                    return path_value
            path_value = clip.data.get("path") or ""
            if path_value:
                return path_value
        return ""

    def _clip_trim_window(self, clip):
        if clip is None:
            return 0.0, 0.0
        data = clip.data if isinstance(clip.data, dict) else {}
        source_start = float(data.get("start", 0.0) or 0.0)
        source_end = float(data.get("end", data.get("start", 0.0) or 0.0) or 0.0)
        if source_end <= source_start:
            source_end = source_start + 1.0
        return max(0.0, source_start), max(source_start, source_end)

    def _extract_audio_segment(self, source_path, start_seconds, end_seconds, output_path):
        if not source_path or not os.path.exists(source_path):
            raise ValueError("The source video file could not be found.")
        duration = max(0.0, float(end_seconds) - float(start_seconds))
        if duration <= 0:
            raise ValueError("The selected clip has no audio duration.")

        import subprocess

        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(float(start_seconds)),
            "-i",
            source_path,
            "-t",
            str(float(duration)),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            output_path,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
            raise ValueError("FFmpeg did not produce an audio file for the selected clip.")

    def _attach_caption_effect(self, clip, vtt_text):
        if not clip:
            return
        try:
            import openshot
            from classes.app import get_app

            app = get_app()
            project = getattr(app, "project", None)
            data = clip.data if isinstance(clip.data, dict) else {}
            effects = data.get("effects") if isinstance(data.get("effects"), list) else []
            effect = openshot.EffectInfo().CreateEffect("Caption")
            effect.Id(project.generate_id())
            caption_json = json.loads(effect.Json())
            caption_text = _first_caption_text(vtt_text) or "Ravi caption"
            caption_json["caption_text"] = caption_text
            effects.append(caption_json)
            data["effects"] = effects
            clip.data = data
            clip.save()
            self._status_message("Captions generated and attached to the clip.", 4000)
        except Exception as ex:
            log.warning("Failed to attach Ravi captions to clip: %s", ex, exc_info=True)
            self._show_error("Captions were created, but OpenShot could not attach them to the selected clip: {}".format(ex))

    def generate_for_clip(self, clip):
        if clip is None:
            raise ValueError("Please select a valid timeline clip.")

        url = self.configured_url()
        if not url:
            raise ValueError("Ravi API URL is not configured. Set it in Edit → Preferences → Advanced.")

        source_path = self._clip_reader_path(clip)
        if not source_path:
            raise ValueError("The selected clip does not have a valid source media file.")
        source_start, source_end = self._clip_trim_window(clip)
        if source_end <= source_start:
            raise ValueError("The selected clip has no valid media range for captioning.")

        if not os.path.exists(source_path):
            raise ValueError("The selected clip's source file is missing: {}".format(source_path))

        audio_temp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        audio_temp.close()
        try:
            self._extract_audio_segment(source_path, source_start, source_end, audio_temp.name)
            client = RaviClient(url)
            response = client.create_caption_job(audio_temp.name)
            job_id = response.get("job_id")
            if not job_id:
                raise ValueError("The Ravi API did not return a valid job id.")

            def worker():
                try:
                    while True:
                        status_payload = client.get_job(job_id)
                        status = str(status_payload.get("status", "")).lower()
                        if status == "completed":
                            result = status_payload.get("result") or {}
                            vtt_text = client.download_result_text(job_id)
                            self._attach_caption_effect(clip, vtt_text)
                            break
                        if status == "failed":
                            error_text = str(status_payload.get("error") or "Caption generation failed.")
                            self._show_error(error_text)
                            self._status_message("Ravi caption generation failed.", 4000)
                            break
                        if status in ("queued", "processing"):
                            time.sleep(2.0)
                            continue
                        self._show_error("Unexpected Ravi caption job status: {}".format(status_payload))
                        break
                except Exception as ex:
                    self._show_error(str(ex))
                finally:
                    try:
                        os.remove(audio_temp.name)
                    except OSError:
                        pass

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            self._status_message("Submitting Ravi caption job for the selected clip...", 3000)
        except Exception as ex:
            try:
                os.remove(audio_temp.name)
            except OSError:
                pass
            raise
