/** Shared public types only. Google credentials must never be added here. */
export type BotTemplate = 'called' | 'position' | 'announcement';
export interface BotName { name: string; handle?: string }
/** Server validates an exact field set for each template. Never arbitrary chat text. */
export interface BotVariables {
  name?: string; handle?: string; members?: BotName[];
  state?: 'waiting' | 'now' | 'not-queued'; position?: number; group?: number;
  waitingCount?: number; groupCount?: number; groupSize?: number;
}

export interface BotPostRequest {
  channelConnectionId: string;
  videoId: string;
  eventId: string;
  createdAt: number;
  templateId: BotTemplate;
  /** OneComme identity for correlation only; not a verified YouTube API channel ID. */
  recipient?: { service: 'youtube'; userId: string };
  variables: BotVariables;
}

export type BotPostStatus = 'accepted' | 'sent' | 'rejected' | 'failed' | 'unknown';
export type BotErrorCode =
  | 'UNAUTHENTICATED' | 'CHANNEL_NOT_LINKED' | 'CHANNEL_MISMATCH' | 'LIVE_NOT_ACTIVE'
  | 'CHAT_UNAVAILABLE' | 'BOT_PERMISSION_REQUIRED' | 'RATE_LIMITED' | 'QUOTA_EXHAUSTED'
  | 'DUPLICATE_CONFLICT' | 'INVALID_MESSAGE' | 'BOT_UNAVAILABLE' | 'DELIVERY_UNKNOWN'
  | 'REQUEST_EXPIRED' | 'SERVICE_DISABLED';

export interface BotPostResponse {
  requestId: string;
  status: BotPostStatus;
  error?: { code: BotErrorCode; message: string; retryAfterSeconds?: number };
}

/** Only the notification fields required for posting leave the local queue. */
export interface BotCandidate {
  eventId: string;
  createdAt: number;
  videoId: string | null;
  templateId: BotTemplate;
  recipient?: { service: 'youtube'; userId: string };
  variables: BotVariables;
}
