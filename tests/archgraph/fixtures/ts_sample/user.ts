import { formatName } from "./format";

export interface User { id: number; name: string; }

export class Account {
  constructor(private user: User) {}
  label(): string { return formatName(this.user.name); }
}
