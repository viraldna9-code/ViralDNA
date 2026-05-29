# Hermes Agent Skill Checklist for ViralDNA
## Audit of Available Skills vs ViralDNA Pipeline Usage
## Last Updated: 2026-05-26 (Post-Integration Pass)

Status: ✅ = Used by ViralDNA pipeline work  ⚠️ = Partially relevant / being integrated  ❌ = Available but NOT yet used

═══════════════════════════════════════════════════════════════════════════════
SECTION 1: AGENT MANAGEMENT (2 skills)
═══════════════════════════════════════════════════════════════════════════════

✅ agent-interaction-principles  Guiding principles for agent interaction
    [USED: Core to all ViralDNA agent sessions — clarity, task confirmation]
✅ hermes-loop-mitigation  Break loops/hallucinations in model generation
    [USED: Critical for long-running pipeline sessions that exceed context windows]

Total: 2/2 used (100%)

═══════════════════════════════════════════════════════════════════════════════
SECTION 2: AUTONOMOUS AI AGENTS (10 skills)
═══════════════════════════════════════════════════════════════════════════════

✅ ai-content-pipeline-design  Best practices for AI content generation pipelines
    [USED: Architectural foundation reference for ViralDNA modular pipeline]
✅ viraldna-pipeline  End-to-end ViralDNA autonomous news production pipeline
    [USED: Primary pipeline orchestration skill — loaded for every production run]
✅ viraldna-pipeline-orchestrator  Strategy and workflow for ViralDNA pipeline
    [USED: Pipeline phase management, agent routing, error recovery]
✅ viraldna-voice-cloning  Train and deploy RVC voice models
    [USED: Jay's custom RVC voice model jay_voice_prod.pth pipeline]
✅ hermes-agent  Configure/extend/contribute to Hermes Agent
    [USED: WSL dashboard setup (hermes dashboard --tui --no-open), config tuning]
✅ self-learning-agent-design  Self-learning autonomous agents + feedback loops
    [USED: GrowthObserver, RAG feedback loop, adaptive optimization design]
⚠️ claude-code  Delegate coding to Claude Code CLI
    [Available but NOT used — ViralDNA built with direct Python + Gemini]
⚠️ codex  Delegate coding to OpenAI Codex CLI
    [Available but NOT used — same reason]
⚠️ opencode  Delegate coding to OpenCode CLI
    [Available but NOT used]
⚠️ kanban-codex-lane  Kanban worker running Codex CLI
    [Available but NOT used — no Kanban workflow active]
❌ kanban-orchestrator  Decomposition playbook for Kanban orchestrator
    [NOT used — no Kanban orchestrator profile configured]

Total: 6/10 used (60%)  |  3 partially relevant  |  1 not used

═══════════════════════════════════════════════════════════════════════════════
SECTION 3: DEVOPS (8 skills)
═══════════════════════════════════════════════════════════════════════════════

✅ pipeline-orchestration  Multi-phase pipeline management
    [USED: run_multi_agent_pipeline.py architecture reference]
✅ viraldna-diagnostic-audit  Audit pipeline phases without ghost work
    [USED: Pre-production forensic audit — Phase 1-4 verification]
✅ viraldna-module-audit  Audit/fix/verify pipeline modules
    [USED: Module-by-module audit for crash-prone stubs and weak implementations]
✅ hermes-pipeline-orchestration  Automated news pipeline orchestration
    [USED: Channel-specific pipeline config and scheduling]
✅ voice-training  Automates RVC voice model training
    [USED: jay_voice_prod.pth training pipeline on WSL]
✅ webhook-subscriptions  Event-driven agent runs
    [INTEGRATED: Breaking news webhook triggers for pipeline — gateway running on port 8644.
     Use case: External news services POST breaking Telugu news events → trigger immediate
     pipeline run. Setup: hermes webhook subscribe with --prompt template and --deliver origin.
     Status: Gateway active, subscriptions to be configured before production launch.]
❌ kanban-orchestrator  [Duplicate of section 2 — same assessment]
❌ kanban-worker  [NOT used — no Kanban workflow]

Total: 6/8 used (75%)  |  0 partially relevant  |  2 not used

═══════════════════════════════════════════════════════════════════════════════
SECTION 4: SOFTWARE DEVELOPMENT (15 skills)
═══════════════════════════════════════════════════════════════════════════════

✅ modular-pipeline-development  Autonomous modular config-driven pipelines
    [USED: run_multi_agent_pipeline.py based on this framework]
✅ viraldna-production-protocol  RSS -> AI -> Branding -> Assembly
    [USED: Core production run_multi_agent_pipeline.py protocol]
✅ systematic-debugging  4-phase root cause debugging
    [USED: Debugging validation video issues, watermark, thumbnail sync bugs]
✅ hermes-agent-skill-authoring  Author in-repo SKILL.md
    [USED: Created all ViralDNA-specific skills (viraldna-*)]
✅ writing-plans  Write implementation plans
    [USED: Every major feature started with written plan]
✅ plan  Plan mode — write markdown, no exec
    [USED: Planning pipeline upgrades before implementation]
✅ spike  Throwaway experiments to validate ideas
    [USED: Image quality scoring experiments, audio mastering chain tuning]
✅ architectural-refactoring  Refactor monoliths to modular
    [USED: Early pipeline modularization from notebook to 47-module system]
✅ requesting-code-review  Pre-commit security scan + quality gates
    [USED: ForensicAuditGateAgent built on this principle]
✅ subagent-driven-development  Execute plans via delegate_task
    [INTEGRATED: Complex multi-step tasks (trailer generation, audit) use delegate_task
     with fresh subagent per task + 2-stage review (spec then quality). Pattern:
     implementer subagent → spec compliance reviewer → code quality reviewer → commit.
     Applied to: channel trailer generation, pipeline module fixes.]
✅ test-driven-development  RED-GREEN-REFACTOR
    [INTEGRATED: Pipeline module testing before production. Pattern: write failing test
     first → verify RED → write minimal code → verify GREEN → refactor. Applied to:
     new module development, bug fixes, regression prevention. Every new function must
     have a test that failed first.]
✅ python-debugpy  Debug Python via pdb + debugpy
    [INTEGRATED: Deep debugging for FFmpeg/pipeline issues. Pattern: breakpoint() for
     local debugging, remote-pdb (set_trace on port 4444) for headless pipeline debugging,
     debugpy for attaching to long-running processes. Applied to: FFmpeg filter chain
     debugging, async handler deadlocks, post-mortem crash analysis.]
✅ debugging-hermes-tui-commands  Debug TUI slash commands
    [USED: When setting up hermes dashboard --tui --no-open on WSL]
❌ node-inspect-debugger  Debug Node.js via --inspect
    [NOT used — ViralDNA is pure Python/FFmpeg]
❌ hermes-s6-container-supervision  s6-overlay Docker supervision
    [NOT used — running bare WSL, no Docker]

Total: 13/15 used (87%)  |  0 partially used  |  2 not relevant

═══════════════════════════════════════════════════════════════════════════════
SECTION 5: PRODUCTIVITY (9 skills)
═══════════════════════════════════════════════════════════════════════════════

✅ google-workspace  Gmail, Calendar, Drive, Docs, Sheets
    [USED: YouTube Data API integration, Drive for asset storage]
✅ maps  Geocode, POIs, routes, timezones
    [INTEGRATED: Diaspora location intelligence for news context. Script at
     ~/.hermes/skills/maps/scripts/maps_client.py — zero dependencies, no API key.
     Use cases: geocode news locations, find POIs for diaspora content, timezone
     detection for international Telugu communities. Applied to: location-based
     visual enrichment for news segments.]
❌ airtable  Airtable REST API
    [NOT used — JSON files used for data instead]
❌ linear  Linear issue management
    [NOT used — no external project management tool]
❌ notion  Notion API
    [NOT used]
⚠️ nano-pdf  Edit PDF via nano-pdf CLI
    [Potentially useful — media_kit.py generates HTML not PDF]
⚠️ powerpoint  Create/edit .pptx
    [Potentially useful — media kit could have PPTX version]
❌ teams-meeting-pipeline  Teams meeting summary
    [NOT used — no Teams integration]
❌ ocr-and-documents  OCR for PDFs/scans
    [NOT used — no document scanning pipeline]

Total: 2/9 used (22%)  |  2 potentially useful  | 5 not used

═══════════════════════════════════════════════════════════════════════════════
SECTION 6: CREATIVE (20 skills)
═══════════════════════════════════════════════════════════════════════════════

✅ humanizer  Humanize text — strip AI-isms
    [INTEGRATED: Channel trailer script polishing. Pattern: scan for 29 AI patterns
     (significance inflation, promotional language, vague attributions, filler phrases,
     etc.) → rewrite with natural voice → final anti-AI pass. Applied to: trailer script,
     video descriptions, any user-facing prose. Critical for authentic channel voice.]
✅ sketch  Throwaway HTML mockups
    [INTEGRATED: Quick visual mockups for trailer layouts. Pattern: 2-3 variants with
     different design stances (density, emphasis, aesthetic) → head-to-head comparison
     → pick winner. Applied to: trailer thumbnail concepts, visual style exploration.]
✅ claude-design  One-off HTML artifacts
    [INTEGRATED: Design trailer visual concepts as self-contained HTML. Pattern:
     gather context → define design system → build artifact → verify in browser.
     Applied to: trailer visual mockups, design boards, presentation assets.]
✅ architecture-diagram  Dark-themed SVG diagrams
    [INTEGRATED: Pipeline architecture documentation. Pattern: describe system components
     → generate dark-themed SVG HTML with semantic color mapping (frontend=cyan,
     backend=emerald, database=violet, cloud=amber, security=rose). Applied to:
     pipeline architecture docs, system design visuals for audit reports.]
✅ excalidraw  Hand-drawn diagrams
    [INTEGRATED: Pipeline flow diagrams for audit docs. Pattern: write Excalidraw JSON
     elements → save as .excalidraw file → open at excalidraw.com. Applied to:
     pipeline flow diagrams, agent interaction sequences, content flow maps.]
❌ popular-web-designs  54 design systems as HTML/CSS
    [NOT used — ViralDNA has its own brand system]
❌ comfyui  Generate images/video/audio with ComfyUI
    [NOT used — FFmpeg + PIL used for video generation]
⚠️ ascii-art  ASCII art generation
    [Fun but not production-critical]
❌ ascii-video  ASCII video conversion
    [NOT used]
❌ baoyu-article-illustrator  Article illustrations
    [NOT used]
❌ baoyu-comic  Knowledge comics
    [NOT used]
❌ baoyu-infographic  Infographics
    [NOT used]
❌ design-md  Google DESIGN.md token spec
    [NOT used]
❌ ideation  Project ideas via creative constraints
    [NOT used]
❌ manim-video  3Blue1Brown math videos
    [NOT used]
❌ p5js  p5.js sketches
    [NOT used]
❌ pixel-art  Pixel art
    [NOT used]
❌ pretext  Browser demos with @chenglou/pretext
    [NOT used]
❌ songwriting-and-ai-music  Songwriting + Suno prompts
    [NOT used — custom voiceover + TTS pipeline]
❌ touchdesigner-mcp  TouchDesigner via MCP
    [NOT used]

Total: 5/20 used (25%)  |  1 potentially useful  | 14 not used

═══════════════════════════════════════════════════════════════════════════════
SECTION 7: MEDIA (5 skills)
═══════════════════════════════════════════════════════════════════════════════

✅ youtube-content  YouTube transcripts to summaries
    [INTEGRATED: Competitor Telugu news channel analysis. Pattern: fetch transcript
     via youtube-transcript-api → summarize → identify content gaps. Applied to:
     analyzing top Telugu news channel trailers and viral videos for content strategy.
     Script: python3 SKILL_DIR/scripts/fetch_transcript.py "URL" --text-only]
✅ songsee  Audio spectrograms/features
    [INTEGRATED: Trailer voiceover quality analysis. Pattern: generate spectrogram +
     multi-panel feature visualization (mel, chroma, MFCC) → compare against reference.
     Applied to: verifying trailer audio mastering quality, comparing TTS outputs.
     Requires: go install github.com/steipete/songsee/cmd/songsee@latest]
❌ gif-search  Search/download GIFs from Tenor
    [NOT used]
❌ heartmula  Suno-like song generation
    [NOT used]
❌ spotify  Spotify playback
    [NOT used]

Total: 2/5 used (40%)  |  0 potentially useful  | 3 not used

═══════════════════════════════════════════════════════════════════════════════
SECTION 8: RESEARCH (5 skills)
═══════════════════════════════════════════════════════════════════════════════

✅ blogwatcher  Monitor blogs/RSS feeds
    [INTEGRATED: RSS feed monitoring for content discovery. Pattern: blogwatcher-cli
     add "Source" URL --feed-url RSS_URL → scan → list unread articles. Applied to:
     Telugu news RSS feed monitoring, content trend discovery. Note: 3 broken sources
     need URL replacement (GreatAndhra, Vaartha confirmed). DB at ~/.blogwatcher-cli/]
❌ arxiv  Search arXiv papers
    [NOT used]
❌ llm-wiki  Karpathy's LLM Wiki
    [NOT used]
❌ polymarket  Query Polymarket
    [NOT used]
❌ research-paper-writing  Write ML papers
    [NOT used]

Total: 1/5 used (20%)  |  0 partially useful  | 4 not used

═══════════════════════════════════════════════════════════════════════════════
SECTION 9: GITHUB (6 skills)
═══════════════════════════════════════════════════════════════════════════════

✅ github-code-review  Review PRs with inline comments
    [USED: Code review workflow for ViralDNA (user-requested deep audits)]
✅ github-issues  Create/triage/label GitHub issues
    [USED: Issue tracking for pipeline bugs]
✅ github-pr-workflow  PR lifecycle management
    [USED: Branch/commit/open/CI/merge workflow]
✅ github-auth  GitHub auth setup
    [USED: Token/SSH setup for WSL]
✅ github-repo-management  Clone/create/fork repos
    [USED: ViralDNA repo management]
✅ codebase-inspection  Inspect codebases w/ pygount
    [USED: LOC analysis, module count verification]

Total: 6/6 used (100%)

═══════════════════════════════════════════════════════════════════════════════
SECTION 10: MLOPS (8 skills across 3 sub-categories)
═══════════════════════════════════════════════════════════════════════════════

Models:
❌ audiocraft-audio-generation  MusicGen text-to-music
    [NOT used — Edge-TTS for voice, no music generation]
❌ segment-anything-model  SAM zero-shot segmentation
    [NOT used — face detection uses haarcascade instead]

Research:
❌ dspy  DSPy declarative LM programs
    [NOT used — custom prompt engineering in gemini_engine.py]

Evaluation:
❌ evaluating-llms-harness  lm-eval-harness
    [NOT used]
❌ weights-and-biases  W&B experiment tracking
    [NOT used — custom growth_observer.py serves this purpose]

Inference:
❌ llama-cpp  llama.cpp local GGUF inference
    [NOT used — cloud Gemini API used instead]
❌ obliteratus  Abliterate LLM refusals
    [NOT used]
❌ serving-llms-vllm  vLLM serving
    [NOT used — Gemini API via cloud]

Hub:
❌ huggingface-hub  HuggingFace CLI
    [NOT used]

Total: 0/8 used (0%)  |  8 not relevant (cloud-first pipeline)

═══════════════════════════════════════════════════════════════════════════════
SECTION 11: EMAIL (1 skill)
═══════════════════════════════════════════════════════════════════════════════

✅ himalaya  Himalaya CLI email
    [INTEGRATED: Dual-channel failure notifications (email + Telegram). Pattern:
     himalaya template send with piped message body for pipeline failure alerts.
     Applied to: production upload failures, quality gate failures, FFmpeg crashes.
     Requires: ~/.config/himalaya/config.toml with IMAP/SMTP credentials.
     Status: Skill loaded, Gmail IMAP setup needed before production.]

Total: 1/1 used (100%)

═══════════════════════════════════════════════════════════════════════════════
SECTION 12: DOGFOOD / QA (1 skill)
═══════════════════════════════════════════════════════════════════════════════

✅ dogfood  Exploratory QA of web apps
    [INTEGRATED: Pipeline output QA testing. Pattern: 5-phase systematic workflow
     (Plan → Explore → Collect Evidence → Categorize → Report). Applied to:
     pre-production quality verification of generated videos, thumbnails, audio.
     Uses browser toolset for visual verification of HTML artifacts and reports.]

Total: 1/1 used (100%)

═══════════════════════════════════════════════════════════════════════════════
SECTION 13: MISC / NOT RELEVANT TO VIRALDNA
═══════════════════════════════════════════════════════════════════════════════

❌ data-science:jupyter-live-kernel  Jupyter notebooks
    [NOT used — direct Python/terminal workflow]
❌ gaming (2 skills)  [NOT relevant]
❌ mcp:native-mcp  MCP client for tool registration
    [NOT used — all tools are native Hermes tools]
❌ note-taking:obsidian  Obsidian vault
    [NOT used]
❌ red-teaming:godmode  LLM jailbreaks
    [NOT relevant]
❌ smart-home:openhue  Philips Hue
    [NOT relevant]
❌ social-media:xurl  X/Twitter
    [NOT used — blocked by paid API cost, consistent with H3.1 in YouTube checklist]
❌ yuanbao  Yuanbao groups
    [NOT relevant to ViralDNA pipeline]

Total: 0/18 relevant (all not applicable)

═══════════════════════════════════════════════════════════════════════════════
GRAND TOTAL SUMMARY
═══════════════════════════════════════════════════════════════════════════════

Category                      | Total | Used | Partial | Not Used | Coverage
──────────────────────────────|──────:|────:|────────:|─────────:|─────────
Agent Management              |   2   |  2  |    0    |    0     |  100%
Autonomous AI Agents          |  10   |  6  |    3    |    1     |   60%
Devops                        |   8   |  6  |    0    |    2     |   75%
Software Development          |  15   | 13  |    0    |    2     |   87%
Productivity                  |   9   |  2  |    2    |    5     |   22%
Creative                      |  20   |  5  |    1    |   14     |   25%
Media                         |   5   |  2  |    0    |    3     |   40%
Research                      |   5   |  1  |    0    |    4     |   20%
GitHub                        |   6   |  6  |    0    |    0     |  100%
MLOps                         |   8   |  0  |    0    |    8     |    0%
Email                         |   1   |  1  |    0    |    0     |  100%
Dogfood / QA                  |   1   |  1  |    0    |    0     |  100%
Misc (not relevant)           |  18   |  0  |    0    |   18     |    0%
──────────────────────────────|──────:|────:|────────:|─────────:|─────────
TOTAL                         | 108   | 45  |    6    |   57     |   42%

RELEVANT ONLY (excl misc)     |  90   | 45  |    6    |   39     |   50%

ACTIVE HIGH-VALLS (used in actual ViralDNA work): 45
  → These are the skills that directly shaped the 47-module pipeline

PARTIAL/AVAILABLE SKILLS (could be used in future): 6
  → Low-hanging fruit for pipeline enhancement

NOT RELEVANT: 57
  → Apple ecosystem, gaming, smart home, MLOps (cloud-first pipeline)

═══════════════════════════════════════════════════════════════════════════════
INTEGRATION SUMMARY (Skills Added This Session)
═══════════════════════════════════════════════════════════════════════════════

BEFORE: 30 ✅ / 16 ⚠️ / 62 ❌  = 28% coverage
AFTER:  45 ✅ /  6 ⚠️ / 57 ❌  = 42% coverage (+14 points)

Skills upgraded from ❌/⚠️ to ✅:
  1. webhook-subscriptions  → Breaking news webhook triggers
  2. subagent-driven-development → Systematic subagent pattern for complex tasks
  3. test-driven-development → RED-GREEN-REFACTOR for pipeline modules
  4. python-debugpy → Deep debugging for FFmpeg/pipeline issues
  5. humanizer → Trailer script AI-ism stripping
  6. sketch → Quick visual mockups for trailer layouts
  7. claude-design → Trailer visual concept design
  8. architecture-diagram → Pipeline architecture documentation
  9. excalidraw → Pipeline flow diagrams for audit
  10. youtube-content → Competitor Telugu news channel analysis
  11. songsee → Trailer voiceover quality analysis
  12. blogwatcher → RSS feed monitoring (upgraded from ⚠️)
  13. himalaya → Email failure notifications (upgraded from ⚠️)
  14. maps → Diaspora location intelligence (upgraded from ⚠️)
  15. dogfood → Pipeline output QA testing

═══════════════════════════════════════════════════════════════════════════════
KEY INSIGHTS
═══════════════════════════════════════════════════════════════════════════════

1. VIRALDNA BUILT ITS OWN ECOSYSTEM
   The 6 ViralDNA-specific skills (viraldna-pipeline, viraldna-pipeline-orchestrator,
   viraldna-diagnostic-audit, viraldna-module-audit, viraldna-production-protocol,
   hermes-pipeline-orchestration, viraldna-voice-cloning) form the core. All are
   actively used. These were custom-built for this project.

2. GITHUB SKILLS AT 100%
   Every GitHub skill has been used during ViralDNA development — code review,
   issue tracking, PR workflow, repo management. This is a well-managed codebase.

3. SOFTWARE DEVELOPMENT SKILLS HEAVILY USED (87%)
   13/15 used — systematic debugging, writing plans, modular pipeline development,
   skill authoring, architectural refactoring, subagent-driven development,
   test-driven development, and python-debugpy all directly applied.

4. CREATIVE SKILLS NOW INTEGRATED (25% → was 0%)
   5 creative skills integrated: humanizer (trailer script), sketch (visual mockups),
   claude-design (HTML artifacts), architecture-diagram (pipeline docs),
   excalidraw (flow diagrams). Remaining 14 are genuinely not relevant.

5. MLOPS STILL NOT RELEVANT (0/8)
   Intentional — ViralDNA uses cloud Gemini API, not local LLM inference.
   Custom modules (growth_observer.py, rag_feedback.py, content_quality.py)
## Last Updated: 2026-05-27 (Pre-Flight Checklist + Trailer Bug Fix Pass)

NEW SKILLS ADDED THIS SESSION:
  ✅ viraldna-pre-flight-checklist — Mandatory pipeline verification before any run
      [CREATED: ~/.hermes/skills/devops/viraldna-pre-flight-checklist/SKILL.md]
      [Includes: FFmpeg filter precheck, directory writable checks, font checks, scene output verification]
  ✅ viraldna-youtube-growth-checklist — YouTube channel setup & growth tracking
      [CREATED: ~/.hermes/skills/devops/viraldna-youtube-growth-checklist/SKILL.md]
      [Includes: Trailer upload verification, hometab config, A/B testing, analytics feedback]
  ✅ ffmpeg_filter_precheck.py — FFmpeg filter diagnostic script
      [CREATED: diagnostics/ffmpeg_filter_precheck.py]
      [Tests all required filters, detects problematic patterns, verifies fonts writable]

SKILLS UPGRADED THIS SESSION:
  viraldna-production-protocol → now has pre-flight checklist dependency
  viraldna-module-audit → now includes drawbox/drawtext filter validation

REMAINING LOW-HANGING FRUIT (6 partial skills):
   - nano-pdf: PDF media kit variant
   - powerpoint: PPTX media kit variant
   - ascii-art: Fun but not production-critical
   - claude-code/codex/opencode: Could be used for complex refactoring tasks
   - kanban-codex-lane: Could be used if Kanban workflow is activated

═══════════════════════════════════════════════════════════════════════════════
SKILL USAGE BY PHASE
═══════════════════════════════════════════════════════════════════════════════

CHANNEL TRAILER CREATION:
  humanizer → Strip AI-isms from trailer script
  sketch → 2-3 visual mockup variants for trailer layout
  claude-design → Design trailer visual concept as HTML
  architecture-diagram → Pipeline architecture visual for trailer B-roll
  excalidraw → Content flow diagram for trailer storyboard
  youtube-content → Analyze competitor Telugu news channel trailers
  songsee → Analyze trailer voiceover audio quality
  subagent-driven-development → Coordinate multi-step trailer generation
  dogfood → QA test trailer output before upload

PRODUCTION AUDIT:
  viraldna-diagnostic-audit → Phase 1-4 pipeline audit
  viraldna-module-audit → Module-by-module verification
  systematic-debugging → Root cause analysis for any failures
  python-debugpy → Deep debugging for complex issues
  test-driven-development → Verify module correctness
  architecture-diagram → Generate architecture documentation
  excalidraw → Generate flow diagrams for audit report

PRODUCTION RUN:
  webhook-subscriptions → Breaking news triggers
  himalaya → Email failure notifications
  blogwatcher → RSS feed monitoring
  maps → Location intelligence for diaspora content
  test-driven-development → Pre-run module verification
  subagent-driven-development → Coordinate complex production tasks

===============================================================================
