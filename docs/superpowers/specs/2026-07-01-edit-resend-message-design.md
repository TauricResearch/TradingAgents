# Edit and Resend Message Feature Design

**Date:** 2026-07-01
**Status:** Approved

## Overview

Add the ability to edit and resend any user message in the Trading Assistant chat interface. When a user edits and resends a message, all subsequent messages (assistant responses, tool messages) are removed and the conversation continues from the edited message.

## User Experience

### Trigger
- A small pencil/edit icon appears when hovering over a user message bubble
- Icon is positioned to the right of the message bubble
- On touch devices: icon is always visible (not just on hover)

### Edit Mode
- Clicking the edit icon populates the input field with the selected message's content
- Input area displays "Editing message..." indicator above the text field
- Send button changes to "Resend" button with different styling
- Pressing Escape cancels edit mode and clears the input back to placeholder state

### Resubmit Flow
1. User modifies the text in the input field
2. User clicks "Resend"
3. The original user message being edited is deleted
4. All messages after it (assistant responses, tool messages) are deleted
5. The edited text is sent as a new user message
6. The LLM responds to the new edited message

## UI Specification

### Edit Icon
- Use Lucide `Pencil` icon (already available in codebase)
- Size: 14px
- Color: `text-slate-400` default, `text-sky-400` on hover
- Position: absolutely positioned to the right of user message bubbles
- Visibility: `opacity-0` default, `group-hover:opacity-100` (visible on parent hover)

### Input Area Changes (Edit Mode)
- Above input: small text "Editing message..." in `text-sky-400 text-xs`
- Send button text changes from "Send" to "Resend"
- Resend button has same styling as Send button

### Cancellation
- Pressing Escape key: cancels edit mode, clears input to placeholder state
- No auto-cancel on unfocus or empty input to avoid accidental data loss

## Technical Specification

### State Changes (useChatStore)

```typescript
// New state
editingMessageId: string | null

// New actions
setEditingMessage(messageId: string | null): void
deleteMessagesAfter(messageId: string): void  // removes msg and all subsequent
```

### Component Changes

#### AgentChatBubble.tsx
1. Add `editingMessageId` and `setEditingMessage` from store
2. Add `editingMessageId` state check in `handleSubmit`:
   - If editing: call `deleteMessagesAfter(editingMessageId)` then set `editingMessageId = null`
3. Add edit button to `MessageBubble` component (only for user messages)
4. Display "Editing message..." indicator in input area when `editingMessageId` is set
5. Handle Escape key to cancel editing

#### LargeChatScreen.tsx
1. Same changes as AgentChatBubble.tsx for consistency

### Message Deletion Logic
- `deleteMessagesAfter(messageId)` finds the index of the message with given ID
- Removes that message AND all messages that come after it in the array
- This ensures the conversation context is consistent when resending

## Files to Modify

1. `web/frontend/src/stores/useChatStore.ts` - add `editingMessageId` state and helper actions
2. `web/frontend/src/components/AgentChatBubble.tsx` - add edit UI and logic
3. `web/frontend/src/components/LargeChatScreen.tsx` - add same edit UI and logic

## Acceptance Criteria

1. User can click edit icon on any user message to populate input
2. Input shows "Editing message..." indicator
3. Send button changes to "Resend"
4. Resending removes original message and all subsequent messages
5. New (edited) message is sent and receives new response
6. Escape cancels edit mode
7. Feature works on both AgentChatBubble and LargeChatScreen
8. Touch devices show edit icon always (not just on hover)