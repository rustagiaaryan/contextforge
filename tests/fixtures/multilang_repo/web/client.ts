export class RouteClient {
  constructor(private prefix: string) {}

  resolve(path: string): string {
    return combine(this.prefix, path);
  }
}

export function combine(prefix: string, path: string): string {
  return `${prefix}/${path}`;
}
