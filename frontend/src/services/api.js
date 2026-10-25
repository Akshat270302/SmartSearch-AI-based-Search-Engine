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
    !Array.isArray(payload.results)
  ) {
    throw new Error("The search service returned an unexpected response.");
  }

  return payload;
}
