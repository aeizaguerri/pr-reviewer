import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getHealth, getProviders, submitReview } from "./client";
import { AppError } from "./errors";

const providerApiKey = "hf_secret_provider_key";
const githubToken = "ghp_secret_github_token";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

describe("API client", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("calls the backend health endpoint using the configured base URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok", neo4j: false }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getHealth()).resolves.toEqual({ status: "ok", neo4j: false });

    expect(fetchMock).toHaveBeenCalledWith("https://api.example.test/health", {
      headers: { Accept: "application/json" },
      method: "GET",
    });
  });

  it("calls the provider discovery endpoint", async () => {
    const providers = [
      {
        key: "cerebras",
        description: "fast free model",
        default_model: "llama",
        key_label: "HuggingFace API Key",
        supports_structured_output: true,
      },
    ];
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ providers }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getProviders()).resolves.toEqual({ providers });

    expect(fetchMock).toHaveBeenCalledWith("https://api.example.test/api/v1/providers", {
      headers: { Accept: "application/json" },
      method: "GET",
    });
  });

  it("submits reviews with the expected endpoint, JSON body, and credential headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ summary: "clean", approved: true, bugs: [], impact_warnings: [] }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await submitReview({
      request: {
        owner: "gentleman-programming",
        repo: "pr-reviewer",
        pr_number: 42,
        provider: "cerebras",
        model: "",
        base_url_override: "",
      },
      providerApiKey,
      githubToken,
    });

    expect(fetchMock).toHaveBeenCalledWith("https://api.example.test/api/v1/review", {
      method: "POST",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${providerApiKey}`,
        "Content-Type": "application/json",
        "X-GitHub-Token": githubToken,
      },
      body: JSON.stringify({
        owner: "gentleman-programming",
        repo: "pr-reviewer",
        pr_number: 42,
        provider: "cerebras",
        model: "",
        base_url_override: "",
      }),
    });
  });

  it("maps non-2xx responses to sanitized typed app errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: `invalid key ${providerApiKey}` }, { status: 401, statusText: "Unauthorized" }),
      ),
    );

    await expect(
      submitReview({
        request: {
          owner: "owner",
          repo: "repo",
          pr_number: 1,
          provider: "openai",
          model: "gpt-4o-mini",
          base_url_override: "",
        },
        providerApiKey,
        githubToken,
      }),
    ).rejects.toMatchObject({ category: "auth", status: 401 });

    await expect(
      submitReview({
        request: {
          owner: "owner",
          repo: "repo",
          pr_number: 1,
          provider: "openai",
          model: "gpt-4o-mini",
          base_url_override: "",
        },
        providerApiKey,
        githubToken,
      }),
    ).rejects.not.toThrow(providerApiKey);
  });

  it("maps network failures to sanitized typed app errors without logging secrets", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error(`network leak ${githubToken}`)));

    await expect(getProviders()).rejects.toBeInstanceOf(AppError);
    await expect(getProviders()).rejects.toMatchObject({ category: "network" });
    await expect(getProviders()).rejects.not.toThrow(githubToken);
    expect(consoleError).not.toHaveBeenCalled();
  });
});
