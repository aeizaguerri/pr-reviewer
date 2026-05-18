export type AppErrorCategory = "network" | "auth" | "validation" | "backend" | "unknown";

export class AppError extends Error {
  readonly category: AppErrorCategory;
  readonly status?: number;

  constructor(category: AppErrorCategory, message: string, status?: number) {
    super(message);
    this.name = "AppError";
    this.category = category;
    this.status = status;
  }
}

export function categoryForStatus(status: number): AppErrorCategory {
  if (status === 401 || status === 403) {
    return "auth";
  }
  if (status === 400 || status === 422) {
    return "validation";
  }
  if (status >= 500) {
    return "backend";
  }
  return "unknown";
}
