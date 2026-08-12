export function addTag(tags: string[], rawTag: string) {
  const tag = rawTag.trim().replace(/\s+/g, ' ');
  if (!tag || tags.includes(tag)) return tags;
  return [...tags, tag];
}

export function removeTag(tags: string[], tag: string) {
  return tags.filter((item) => item !== tag);
}
