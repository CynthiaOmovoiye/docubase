/**
 * useChat hook.
 *
 * Manages chat session state for:
 * - Single twin chat (twinId provided)
 * - Workspace-wide chat (workspaceId provided — routing happens server-side)
 * - Public share sessions (publicSlug provided, no auth)
 * - Resumed sessions (resumeSessionId provided — loads existing history)
 */

import { useState, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Message, ChatSession, ChatSessionSummary } from "@/types";

interface UseChatOptions {
  twinId?: string;
  workspaceId?: string;
  publicSlug?: string;
  resumeSessionId?: string | null;
}

interface UseChatReturn {
  session: ChatSession | null;
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  sendMessage: (content: string) => Promise<void>;
  startSession: () => Promise<void>;
  startNewSession: () => void;
}

export function useChat({ twinId, workspaceId, publicSlug, resumeSessionId }: UseChatOptions): UseChatReturn {
  const [session, setSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // When resumeSessionId changes, load that session's history
  useEffect(() => {
    if (!resumeSessionId) return;
    setError(null);
    setIsLoading(true);
    api
      .get<{ session_id: string; messages: Message[] }>(`/chat/session/${resumeSessionId}/history`)
      .then((res) => {
        setSession({ session_id: resumeSessionId, workspace_id: "", twin_id: twinId ?? null, created_at: "" });
        setMessages(res.data.messages);
      })
      .catch(() => setError("Failed to load session history"))
      .finally(() => setIsLoading(false));
  }, [resumeSessionId]);

  const startSession = useCallback(async () => {
    setError(null);
    try {
      let response;
      if (publicSlug) {
        response = await api.post(`/chat/public/${publicSlug}/session`);
      } else if (twinId) {
        response = await api.post(`/chat/twin/${twinId}/session`);
      } else if (workspaceId) {
        response = await api.post(`/chat/workspace/${workspaceId}/session`);
      } else {
        throw new Error("Must provide twinId, workspaceId, or publicSlug");
      }
      setSession(response.data);
      setMessages([]);
    } catch {
      setError("Failed to start session");
    }
  }, [twinId, workspaceId, publicSlug]);

  const startNewSession = useCallback(() => {
    setSession(null);
    setMessages([]);
    setError(null);
  }, []);

  const sendMessage = useCallback(
    async (content: string) => {
      let currentSession = session;
      if (!currentSession) {
        setError(null);
        try {
          let response;
          if (publicSlug) {
            response = await api.post(`/chat/public/${publicSlug}/session`);
          } else if (twinId) {
            response = await api.post(`/chat/twin/${twinId}/session`);
          } else if (workspaceId) {
            response = await api.post(`/chat/workspace/${workspaceId}/session`);
          } else {
            throw new Error("Must provide twinId, workspaceId, or publicSlug");
          }
          currentSession = response.data as ChatSession;
          setSession(currentSession);
          setMessages([]);
        } catch {
          setError("Failed to start session");
          return;
        }
      }

      const optimisticMessage: Message = {
        id: `temp-${Date.now()}`,
        role: "user",
        content,
        routed_twin_id: null,
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, optimisticMessage]);
      setIsLoading(true);
      setError(null);

      try {
        let response;
        if (publicSlug) {
          response = await api.post(
            `/chat/public/${publicSlug}/message`,
            { content },
            { params: { session_id: currentSession.session_id } },
          );
        } else {
          response = await api.post(
            `/chat/session/${currentSession.session_id}/message`,
            { content },
          );
        }
        const assistantMessage: Message = response.data;
        setMessages((prev) => [...prev, assistantMessage]);
      } catch {
        setError("Failed to send message");
        setMessages((prev) => prev.filter((m) => m.id !== optimisticMessage.id));
      } finally {
        setIsLoading(false);
      }
    },
    [session, publicSlug, twinId, workspaceId],
  );

  return { session, messages, isLoading, error, sendMessage, startSession, startNewSession };
}

// ─── Session listing ──────────────────────────────────────────────────────────

export function useTwinSessions(twinId: string | undefined) {
  return useQuery({
    queryKey: ["chat", "sessions", twinId],
    queryFn: async () => {
      const res = await api.get<ChatSessionSummary[]>(`/chat/twin/${twinId}/sessions`);
      return res.data;
    },
    enabled: !!twinId,
    staleTime: 1000 * 15,
  });
}

export function useWorkspaceSessions(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["chat", "workspace-sessions", workspaceId],
    queryFn: async () => {
      const res = await api.get<ChatSessionSummary[]>(`/chat/workspace/${workspaceId}/sessions`);
      return res.data;
    },
    enabled: !!workspaceId,
    staleTime: 1000 * 15,
  });
}
