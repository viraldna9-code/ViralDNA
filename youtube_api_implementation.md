# ViralDNA — YouTube API Services Implementation Document

## Overview
ViralDNA is an automated Telugu diaspora news pipeline that uses YouTube Data API v3 to upload and manage video content. The pipeline runs on a local Linux (WSL) server and publishes 1 main video + 2-3 shorts per day to a single YouTube channel.

## API Client Details
- Project: theviraldna (Project Number: 192793181154)
- OAuth Client ID: 192793181154-sikhrle9g29unlopmk6vnrjnitpivu2k.apps.googleusercontent.com
- Auth Method: OAuth 2.0 Desktop Application (InstalledAppFlow)
- Scopes: youtube.upload, youtube.force-ssl, youtube.readonly

## YouTube API Services Used

### 1. Data API v3
The following endpoints are used:

#### videos().insert() — Video Upload
- Uploads main video (1920x1080, ~60-90s) and shorts (1080x1920, <60s)
- Sets title, description, tags, category, privacy status
- Uses resumable upload (MediaFileUpload) for reliability
- Frequency: 3-4 calls per day

#### thumbnails().set() — Custom Thumbnails
- Uploads branded thumbnail for each video
- Thumbnails are auto-generated with title overlay and ViralDNA watermark
- Frequency: 3-4 calls per day

#### commentThreads().insert() — Pinned Comments
- Posts a pinned comment on each uploaded video with CTA
- Comment includes link to main video or channel
- Frequency: 3-4 calls per day

#### playlistItems().insert() — Playlist Management
- Adds uploaded videos to topic-based playlists (e.g., Politics, NRI News)
- Frequency: 3-4 calls per day

#### videos().list() — Video Status Check
- Verifies upload completion and retrieves video metadata
- Frequency: 2-3 calls per day

#### channels().list() — Channel Metadata
- Reads channel statistics for analytics reporting
- Frequency: 1 call per day

### 2. Analytics API (Planned)
- Reads video-level metrics: views, watch time, retention, CTR
- Used for internal performance reporting and content optimization
- Currently implemented as stub; full integration planned

## Data Flow
1. RSS feeds → Topic discovery (Serper API + Gemini)
2. Gemini Flash → Script generation (1 main + 3 shorts)
3. Edge-TTS → Voice synthesis (English + Telugu)
4. FFmpeg → Video assembly (Kenburns, branding, captions)
5. YouTube Data API → Upload + thumbnail + comment + playlist
6. Internal analytics → Performance reporting

## Quota Usage Estimate
- Video uploads: 3-4 × 1,600 = 4,800-6,400 units/day
- Thumbnails: 3-4 × 50 = 150-200 units/day
- Comments: 3-4 × 50 = 150-200 units/day
- Playlists: 3-4 × 50 = 150-200 units/day
- Status checks: ~100 units/day
- Total: ~5,300-7,400 units/day (current)
- Projected (2x daily runs): ~12,000-14,800 units/day

## Architecture
- Language: Python 3.10+
- Libraries: google-api-python-client, google-auth-oauthlib
- Platform: WSL (Windows Subsystem for Linux)
- Scheduling: Hermes cron jobs
- Storage: Local filesystem (/home/jay/ViralDNA/)

## Content Type
- Original news commentary for Telugu NRI audience
- AI-assisted scripting with human-in-the-loop review
- Bilingual: English and Telugu
- Categories: Politics, Immigration, NRI Affairs, Culture

## Monetization
- Standard YouTube Partner Program ad revenue only
- No sale of YouTube data to third parties
- No paid subscriptions or API reselling
