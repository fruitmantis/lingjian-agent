// Parse locally; only the extracted Key goes to the existing login endpoint.
export async function readIdentityKeyFile(file: File): Promise<string> {
  if (!/\.txt$/i.test(file.name)) throw new Error("请选择下载的 .txt 身份凭据文件");
  if (file.size > 16 * 1024) throw new Error("文件过大，请选择伴飞下载的身份凭据文件（不超过 16 KB）");
  let content: string;
  try { content = await file.text(); }
  catch { throw new Error("无法读取文件，请重新选择，或粘贴 Key 登录"); }
  // Both the downloaded document and a plain Key have one standalone Key line.
  // Never guess between credentials or extract a valid-looking substring.
  const candidates = content.split(/\r?\n/).map(line => line.trim()).filter(line => line.startsWith("bf_"));
  if (candidates.length > 1) throw new Error("文件包含多个 Key，请选择只含一个身份的凭据文件");
  if (candidates.length !== 1 || !/^bf_[A-Za-z0-9_-]{43}$/.test(candidates[0]) || content.includes("\0")) {
    throw new Error("未找到有效的身份 Key，请选择伴飞下载的凭据文件，或粘贴 Key 登录");
  }
  return candidates[0];
}
