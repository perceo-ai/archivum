import { formatName } from "./format";
export function Widget(props: { name: string }) {
  return formatName(props.name);
}
