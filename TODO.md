# Leave Bot TODOs

## Thread Context Handling
- [ ] Thread replies should trigger parsing without requiring trigger keywords
- [ ] When parsing a thread reply, include the original message (thread parent) as context for the LLM
- [ ] The LLM prompt should receive both the original message and the follow-up so it understands the full conversation

**Files to modify:**
- `leave_bot/bot/handlers.py` - Adjust thread detection logic, fetch parent message via `conversations.replies` or `conversations.history`
- `leave_bot/bot/parser.py` - Update prompt to accept conversation context, not just a single message

## Slack User Import Scope
- [ ] Only import users who are members of the configured leave channel (`SLACK_CHANNEL_ID`)
- [ ] Use `conversations.members` API to get channel member list, then fetch user info for those IDs only

**Files to modify:**
- `leave_bot/web/routes/users.py` - Update `/api/users/import/slack` endpoint

## Multi-day Calendar Events
- [ ] For consecutive leave days, create a single calendar event spanning the full range instead of one event per day
- [ ] Group consecutive dates before creating events (e.g., Jan 5-10 = one event with start=Jan 5, end=Jan 11)
- [ ] Handle gaps correctly (e.g., Jan 5-7 + Jan 10-12 = two separate spanning events)

**Files to modify:**
- `leave_bot/services/calendar.py` - Add logic to merge consecutive dates
- `leave_bot/services/sync.py` - Adjust sync orchestration to handle merged events

## Switch to OpenAI Responses API
- [ ] Replace `beta.chat.completions.parse` with the Responses API
- [ ] Use structured output via JSON schema in Responses API format
- [ ] Set reasoning effort to `minimal` as per tech spec

**Reference:** https://platform.openai.com/docs/api-reference/responses

**Files to modify:**
- `leave_bot/bot/parser.py` - Rewrite to use `client.responses.create()` with `text.format.type = "json_schema"`
