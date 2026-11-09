# Ravi Caption API Integration

This document describes the Ravi caption-generation flow currently implemented
in OpenShot and the HTTP contract a Ravi API server must provide.

## Configuration

Set **Ravi API URL** in **Edit → Preferences → Advanced**. This value is the
API server's base URL, for example:

```text
https://ravi.example.com
```

If no scheme is supplied, the client assumes `https://`. The API paths below
are appended to this base URL. The Preferences **Check** button calls the
health endpoint.

The Ravi integration is separate from OpenShot's ComfyUI integration.

## OpenShot Flow

1. Select a timeline clip and choose **AI Tools → Ravi API → Generate Captions**
   from its context menu. This menu item is shown when a Ravi API URL is set.
2. OpenShot reads the clip's source file and its `start`/`end` source-media
   range.
3. FFmpeg extracts that range to a temporary WAV file using PCM signed 16-bit
   audio at 16 kHz. The temporary file is removed after job processing.
4. OpenShot uploads the WAV and caption options to Ravi.
5. OpenShot polls the job status every two seconds in a background thread.
6. On completion, OpenShot downloads a WebVTT result and currently uses its
   first caption cue as the text for a native Caption effect on the selected
   clip.

The extraction and initial job submission happen before the polling thread is
started. Polling and result retrieval happen asynchronously.

## HTTP API Contract

All responses must use successful HTTP status codes for successful operations;
OpenShot calls `raise_for_status()` and reports request failures. Requests use
the app's configured TLS certificate verification. The current client does not
send an API key, bearer token, or other authentication header.

### 1. Health check

```http
GET /api/v1/health/
```

Expected JSON response:

```json
{
  "status": "ok",
  "service": "ravi-api"
}
```

Both values are checked (case-insensitively). A different response is treated
as an unsuccessful connection check.

### 2. Create a caption job

```http
POST /api/v1/captions/jobs
Content-Type: multipart/form-data
```

Multipart fields:

| Field | Type | Current value/default | Description |
|---|---|---|---|
| `audio` | file | WAV file | Selected clip's extracted audio |
| `language` | string | `en` | Requested transcription/caption language |
| `words_per_caption` | integer | `4` | Requested words per caption |
| `max_line_chars` | integer | `24` | Requested maximum characters per caption line |

Expected JSON response:

```json
{
  "job_id": "job-identifier"
}
```

The job identifier is used in the two following requests. Other response
properties are permitted but currently ignored by OpenShot.

### 3. Read job status

```http
GET /api/v1/captions/jobs/{job_id}/
```

Expected JSON response examples:

```json
{
  "job_id": "job-identifier",
  "status": "processing"
}
```

```json
{
  "job_id": "job-identifier",
  "status": "completed"
}
```

```json
{
  "job_id": "job-identifier",
  "status": "failed",
  "error": "A human-readable failure message"
}
```

OpenShot recognizes these status values (case-insensitively):

- `queued` and `processing`: continue polling, every two seconds.
- `completed`: download the result.
- `failed`: stop and show the `error` value, or a generic failure message.

Any other status is treated as unexpected and stops processing. The optional
`result` property is currently not used.

### 4. Download the result

```http
GET /api/v1/captions/jobs/{job_id}/result/
```

Return the WebVTT document as the raw response body, not a JSON wrapper. For
example:

```text
WEBVTT

00:00:00.000 --> 00:00:02.000
Example caption

00:00:02.000 --> 00:00:04.000
Another caption
```

The client saves the response body and reads it as UTF-8 text. While OpenShot
currently downloads the complete VTT, only the first caption cue is attached
to the clip. Full multi-cue caption import/placement is not implemented yet.

## Endpoint Summary

| Method | Path | Expected response |
|---|---|---|
| `GET` | `/api/v1/health/` | JSON with `status: "ok"` and `service: "ravi-api"` |
| `POST` | `/api/v1/captions/jobs` | JSON containing `job_id` |
| `GET` | `/api/v1/captions/jobs/{job_id}/` | JSON containing recognized `status` |
| `GET` | `/api/v1/captions/jobs/{job_id}/result/` | Raw WebVTT body |

## Django REST Framework Notes

A DRF implementation can use separate views or a viewset with these URL
patterns. Ensure that:

- The create view accepts `multipart/form-data` and reads the uploaded file
  from `request.FILES["audio"]`.
- The create response includes a non-empty `job_id`.
- The status view returns one of the recognized status values while the job is
  active and after it finishes.
- The result view returns WebVTT as the raw body (for example with
  `Content-Type: text/vtt; charset=utf-8`).
- Failures return a non-2xx response or a job with `status: "failed"` and a
  useful `error` message.

The client currently has no authentication-header support. If the server
requires authentication, the client will need a corresponding change.

## Implementation References

- Client and caption service: [src/classes/ravi_client.py](./src/classes/ravi_client.py)
- Preferences setting and connection check: [src/windows/preferences.py](./src/windows/preferences.py)
- Timeline context menu: [src/windows/views/timeline.py](./src/windows/views/timeline.py)
- Main-window action: [src/windows/main_window.py](./src/windows/main_window.py)
- Default setting: [src/settings/_default.settings](./src/settings/_default.settings)
