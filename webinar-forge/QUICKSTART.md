# Quickstart

Five minutes to a rendered webinar, assuming a fresh Ubuntu or Debian server.

## 1. Unpack and install

```bash
unzip webinar-forge-1.0.0.zip
cd webinar-forge
./install.sh
```

This installs ffmpeg, chromium, python3 and the Node dependencies. It does
**not** install torch — that comes next, and it is the slow part.

## 2. Try it without the ML stack first

```bash
npm run mock-engine        # in one shell
node bin/webinar-forge build projects/example/project.json    # in another
```

You get a real MP4 with real slide timings and silent narration. This proves
ffmpeg, chromium and the pipeline all work before you spend time on torch.

## 3. Install the real voice engine

```bash
./install.sh --engine      # downloads torch + Chatterbox, several minutes
./engine/start.sh          # first run also downloads model weights
```

## 4. Add a voice

Record 10–30 seconds of clean speech, then:

```bash
node bin/webinar-forge add-voice my-voice /path/to/sample.wav
node bin/webinar-forge voices
```

## 5. Build your webinar

```bash
node bin/webinar-forge init projects/my-webinar
# edit projects/my-webinar/project.json — set "voice": { "name": "my-voice" }
node bin/webinar-forge build projects/my-webinar/project.json
```

Output lands in `output/<project-name>/dist/<project-name>.mp4`.

## Docker instead

```bash
docker compose -f docker/docker-compose.yml up -d engine
docker compose -f docker/docker-compose.yml run --rm build projects/example/project.json
```

## When something breaks

```bash
node bin/webinar-forge doctor
```

It checks every binary, the Node modules, the engine connection and the
installed voices, and names what to fix.
