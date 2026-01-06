# OpenCue - Development Tracker

## Current Focus: Milestone 1.1 - Basic Audio Overlay

### In Progress
- [ ] Firefox extension skeleton
- [ ] Python backend foundation

### Milestone 1.1 Tasks
- [x] Project structure setup
- [x] OpenCue specification (spec/OPENCUE-SPEC.md)
- [ ] Firefox extension manifest.json
- [ ] Extension content.js (Netflix injection)
- [ ] Extension background.js (WebSocket client)
- [ ] Extension popup (connection status)
- [ ] Netflix subtitle interception
- [ ] Python backend FastAPI skeleton
- [ ] WebSocket server (localhost:8765)
- [ ] Profanity word list (JSON, ~500 words)
- [ ] Word list matcher (regex-based)
- [ ] Subtitle → backend pipeline
- [ ] Overlay command → extension pipeline
- [ ] Audio muting implementation
- [ ] Basic dashboard (connection status, recent events)
- [ ] End-to-end testing with Netflix content

---

## Backlog

### Milestone 1.2: Contextual Analysis
- [ ] Subtitle text windowing (3-5 second windows)
- [ ] Context rules engine
- [ ] Ollama integration
- [ ] LLM prompt engineering for context analysis
- [ ] Confidence scoring (0-1 scale)
- [ ] High confidence = auto-overlay
- [ ] Low confidence = log for review

### Milestone 1.3: User Profiles & Word Management
- [ ] SQLite database setup
- [ ] Profile data model
- [ ] Profile CRUD API endpoints
- [ ] Profile switching in extension
- [ ] Dashboard: profile management UI
- [ ] Dashboard: word list management UI
- [ ] Word display format (2 chars + asterisks)
- [ ] Word reveal on hover (2 second timeout)
- [ ] Pre-populated default word lists
- [ ] Custom word addition
- [ ] Profile export (JSON)
- [ ] Profile import
- [ ] PIN protection (optional)

### Milestone 2.1: Video Blur Overlay
- [ ] Overlay positioning over Netflix video
- [ ] CSS blur implementation
- [ ] Blur intensity levels (light/medium/heavy)
- [ ] Smooth fade in/out transitions
- [ ] Manual blur trigger for testing
- [ ] WebSocket blur commands

### Milestone 2.2: Subtitle-Based Scene Detection
- [ ] Violence keyword list
- [ ] Sexual content keyword list
- [ ] LLM scene classification prompts
- [ ] Pre-emptive blur timing (trigger early)
- [ ] Scene duration estimation
- [ ] Combine audio mute + video blur

### Milestone 2.3: Content Category System
- [ ] Category taxonomy data structure
- [ ] Hierarchical category storage
- [ ] Parent/child inheritance logic
- [ ] Per-category action settings (mute vs blur vs both)
- [ ] Category sensitivity levels
- [ ] Dashboard: category tree UI

### Milestone 3.1: .opencue File Generation
- [ ] Real-time event recording during playback
- [ ] Content identification (title + source + ID)
- [ ] .opencue file write on playback end
- [ ] File storage location management
- [ ] File naming convention

### Milestone 3.2: .opencue File Playback
- [ ] .opencue file discovery on content start
- [ ] File loading and parsing
- [ ] Profile-based event application
- [ ] Real-time mode vs file mode toggle
- [ ] Seamless mode switching

### Milestone 3.3: Preprocessing Mode
- [ ] Preprocessing job queue
- [ ] Background job worker
- [ ] Progress tracking
- [ ] Deeper LLM analysis (larger context)
- [ ] Completion notification
- [ ] Dashboard: preprocessing queue UI

### Milestone 3.4: .opencue File Encryption
- [ ] Machine ID generation
- [ ] Encryption key derivation
- [ ] Fernet encryption implementation
- [ ] Encrypted file format
- [ ] Decryption on load
- [ ] Key storage security
- [ ] Key loss handling

---

## Future Considerations

### Audio Analysis
- Speech-to-text for non-subtitled content
- Music/sound classification
- Tone analysis

### Video Frame Analysis
- Frame sampling
- NSFW detection models
- Violence detection models
- GPU inference optimization

### Multi-Platform Support
- Disney+
- HBO Max
- Amazon Prime
- Hulu
- Platform-specific subtitle extraction

### Community Features
- Shared overlay profiles (anonymized)
- Community word list contributions
- Crowdsourced context rules

---

## Completed
- [x] Repository setup
- [x] README.md
- [x] LICENSE (MIT)
- [x] FAQ
- [x] ROADMAP
- [x] spec/OPENCUE-SPEC.md

---

## Notes

- Focus on one milestone at a time
- Test thoroughly before moving on
- Keep the dashboard simple initially
- Document as we go
- Commit frequently to git
- Use "overlay" terminology (not "filter") for legal compliance
