import React from "react";

import {
  AelinAction,
  AelinCitation,
  AelinImageInput,
  AelinToolStep,
} from "../../api";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  ts: number;
  expression?: string;
  pending?: boolean;
  citations?: AelinCitation[];
  citation_snippets?: Record<string, string>;
  actions?: AelinAction[];
  images?: AelinImageInput[];
  tool_trace?: AelinToolStep[];
};

export type ChatSession = {
  id: string;
  title: string;
  messages: ChatMessage[];
  updated_at: number;
};

export type PendingImage = {
  id: string;
  dataUrl: string;
  name: string;
};

export type TrackingSheetState = {
  action: AelinAction;
  messageId: string;
};

export type HandoffFXState = {
  title: string;
  detail: string;
};

export type AelinDeskBridgePayload = {
  sessionId: string;
  workspace: string;
  messageId?: number;
  contactId?: number;
  focusQuery?: string;
  highlightSource?: string;
  resumePrompt?: string;
};

export type AelinProps = {
  embedded?: boolean;
  workspace?: string;
  onOpenDesk?: (payload: AelinDeskBridgePayload) => void;
  onRequestClose?: () => void;
};

export type ResultCard = {
  id: string;
  title: string;
  value: string;
  subtitle?: string;
  accent: string;
  icon: React.ReactNode;
};

export type TrackingAckFilter = "all" | "unacked" | "acked";

export type GroupedMessage = {
  message: ChatMessage;
  isGroupStart: boolean;
};
