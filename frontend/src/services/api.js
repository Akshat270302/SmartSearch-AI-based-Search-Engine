const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

function getErrorMessage(status, detail) {
  if (status === 502) {
    return "The search service is unavailable right now. Please check that the backend and SSH tunnel are running.";
  }

  if (status >= 500) {
    return "The search service encountered a problem. Please try again shortly.";
  }

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  return `The search request could not be completed (HTTP ${status}).`;
}

function getDocumentErrorMessage(status, detail) {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (status >= 500) {
    return "The document service encountered a problem. Please try again shortly.";
  }
  return `The document request could not be completed (HTTP ${status}).`;
}

async function getDocumentResponsePayload(response) {
  let payload;
  try {
    payload = await response.json();
  } catch {
    if (!response.ok) {
      throw new Error(getDocumentErrorMessage(response.status));
    }
    throw new Error("The document service returned an invalid response.");
  }

  if (!response.ok) {
    throw new Error(getDocumentErrorMessage(response.status, payload?.detail));
  }
  return payload;
}

export async function uploadDocument(file, { signal } = {}) {
  const formData = new FormData();
  formData.append("file", file);

  let response;
  try {
    response = await fetch(`${API_BASE_URL}/documents/extract`, {
      method: "POST",
      body: formData,
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(
      "Unable to reach the document service. Check that the backend is running.",
    );
  }

  const payload = await getDocumentResponsePayload(response);
  if (
    !payload ||
    typeof payload.document_id !== "string" ||
    !payload.document_id.trim() ||
    typeof payload.filename !== "string" ||
    !Array.isArray(payload.chunks)
  ) {
    throw new Error("The document service returned an unexpected response.");
  }
  return payload;
}

export async function askDocument({ documentId, query, topK, signal }) {
  const body = { document_id: documentId, query };
  if (topK !== undefined) body.top_k = topK;

  let response;
  try {
    response = await fetch(`${API_BASE_URL}/documents/ask`, {
      method: "POST",
      signal,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(
      "Unable to reach the document service. Check that the backend is running.",
    );
  }

  const payload = await getDocumentResponsePayload(response);
  if (
    !payload ||
    typeof payload.answer !== "string" ||
    !payload.answer.trim() ||
    !Array.isArray(payload.sources)
  ) {
    throw new Error("The document service returned an unexpected response.");
  }
  return payload;
}

export async function askQuestion(query, { signal } = {}) {
  const params = new URLSearchParams({ q: query });
  const url = `${API_BASE_URL}/ask?${params.toString()}`;

  let response;
  try {
    response = await fetch(url, { signal });
  } catch (error) {
    if (error.name === "AbortError") {
      throw error;
    }

    throw new Error(
      "Unable to reach the search service. Check that the backend and SSH tunnel are running.",
    );
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    if (!response.ok) {
      throw new Error(getErrorMessage(response.status));
    }

    throw new Error("The search service returned an invalid response.");
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(response.status, payload?.detail));
  }

  if (
    !payload ||
    typeof payload.summary !== "string" ||
    !Array.isArray(payload.results) ||
    (payload.citations !== undefined && !Array.isArray(payload.citations))
  ) {
    throw new Error("The search service returned an unexpected response.");
  }

  return payload;
}

export async function searchQuestion(query, { signal, category } = {}) {
  const params = new URLSearchParams({ q: query });
  if (category) params.set("category", category);

  let response;
  try {
    response = await fetch(`${API_BASE_URL}/search?${params}`, { signal });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(
      "Unable to reach the search service. Check that the backend and SSH tunnel are running.",
    );
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("The search service returned an invalid response.");
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(response.status, payload?.detail));
  }

  if (!payload || !Array.isArray(payload.results)) {
    throw new Error("The search service returned an unexpected response.");
  }

  return payload;
}

export async function streamQuestion(
  query,
  { signal, onEvent, results, conversationHistory } = {},
) {
  const hasContext = Array.isArray(results);
  const params = new URLSearchParams({ q: query });
  const contextBody = hasContext
    ? {
        results,
        ...(Array.isArray(conversationHistory)
          ? { conversation_history: conversationHistory }
          : {}),
      }
    : null;
  const request = hasContext
    ? fetch(`${API_BASE_URL}/ask/stream/context?${params}`, {
        method: "POST",
        signal,
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(contextBody),
      })
    : fetch(`${API_BASE_URL}/ask/stream?${params}`, {
        signal,
        headers: { Accept: "text/event-stream" },
      });
  let response;
  try {
    response = await request;
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(
      "Unable to reach the search service. Check that the backend and SSH tunnel are running.",
    );
  }

  if (!response.ok || !response.body) {
    let detail = "";
    try {
      detail = (await response.json())?.detail;
    } catch {
      // Use the status-based message when the error body is not JSON.
    }
    throw new Error(getErrorMessage(response.status, detail));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const event of events) {
        const dataLine = event
          .split("\n")
          .find((line) => line.startsWith("data:"));
        if (!dataLine) continue;

        try {
          onEvent?.(JSON.parse(dataLine.slice(5).trim()));
        } catch {
          onEvent?.({
            type: "error",
            message: "The search service sent an invalid stream event.",
          });
        }
      }

      if (done) {
        if (buffer.trim()) {
          const dataLine = buffer
            .split("\n")
            .find((line) => line.startsWith("data:"));
          if (dataLine) {
            try {
              onEvent?.(JSON.parse(dataLine.slice(5).trim()));
            } catch {
              onEvent?.({
                type: "error",
                message: "The search service sent an invalid stream event.",
              });
            }
          }
        }
        break;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
