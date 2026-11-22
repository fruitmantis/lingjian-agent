"use client";

import Link from "next/link";
import { useState } from "react";

export type SubCapabilityItem = { parent: string; name: string };

export type CapabilityL2Tag = {
  id: string;
  name: string;
  category: string;
  parentId: string;
  parentName: string;
  description: string | null;
  enabled: boolean;
  sortOrder: number;
  isPreset: boolean;
  level: 2;
};

export type CapabilityL1Tag = {
  id: string;
  name: string;
  category: string;
  description: string | null;
  enabled: boolean;
  sortOrder: number;
  isPreset: boolean;
  level: 1;
  children: CapabilityL2Tag[];
};

export type CapabilityCategoryNode = {
  id: string;
  name: string;
  code: string | null;
  description: string | null;
  enabled: boolean;
  sortOrder: number;
  isPreset: boolean;
  tags: CapabilityL1Tag[];
};

export function splitCapabilityNames(value: string | null | undefined): string[] {
  if (!value) return [];
  const seen = new Set<string>();
  const result: string[] = [];
  for (const part of value.split(/[,，、;；\n]+/)) {
    const trimmed = part.trim();
    if (trimmed && !seen.has(trimmed)) {
      seen.add(trimmed);
      result.push(trimmed);
    }
  }
  return result;
}

export function groupPartnerCapabilities(
  capabilities: string | null | undefined,
  subCapabilities: SubCapabilityItem[] | null | undefined,
): Array<{ parent: string; children: string[] }> {
  const subs = subCapabilities || [];
  const l1Order = [...splitCapabilityNames(capabilities)];
  for (const sub of subs) {
    if (!l1Order.includes(sub.parent)) {
      l1Order.push(sub.parent);
    }
  }
  return l1Order.map((parent) => ({
    parent,
    children: subs.filter((sub) => sub.parent === parent).map((sub) => sub.name),
  }));
}

export function buildCapabilityFilterGroups(
  capTree: CapabilityCategoryNode[],
  capabilityOptions: string[],
): Array<{ name: string; values: string[] }> {
  if (!capTree.length) return [{ name: "能力标签", values: capabilityOptions }];
  const known = new Set(capTree.flatMap((cat) => cat.tags.map((tag) => tag.name)));
  const groups = capTree
    .map((cat) => ({ name: cat.name, values: cat.tags.map((tag) => tag.name) }))
    .filter((group) => group.values.length > 0);
  const extra = capabilityOptions.filter((value) => !known.has(value));
  if (extra.length) groups.push({ name: "其他能力标签", values: extra });
  return groups.length ? groups : [{ name: "能力标签", values: capabilityOptions }];
}

export function buildSubCapabilityFilterGroups(
  capTree: CapabilityCategoryNode[],
  partners: Array<{ sub_capabilities?: SubCapabilityItem[] | null }>,
): Array<{ name: string; values: string[] }> {
  const groups: Array<{ name: string; values: string[] }> = [];
  const knownPairs = new Set<string>();
  for (const cat of capTree) {
    for (const l1 of cat.tags) {
      if (!l1.children.length) continue;
      const values = l1.children.map((child) => {
        const pair = `${l1.name}/${child.name}`;
        knownPairs.add(pair);
        return pair;
      });
      groups.push({ name: l1.name, values });
    }
  }
  const extraPairs = new Set<string>();
  for (const partner of partners) {
    for (const sub of partner.sub_capabilities || []) {
      const pair = `${sub.parent}/${sub.name}`;
      if (!knownPairs.has(pair)) extraPairs.add(pair);
    }
  }
  if (extraPairs.size > 0) {
    groups.push({
      name: "其他细分能力",
      values: [...extraPairs].sort((a, b) => a.localeCompare(b, "zh-CN")),
    });
  }
  return groups;
}

export function matchesPartnerCapabilities(
  capabilities: string | null | undefined,
  subCapabilities: SubCapabilityItem[] | null | undefined,
  selectedL1: string[],
  selectedSubPairs: string[],
): boolean {
  if (!selectedL1.length && !selectedSubPairs.length) return true;
  const subs = subCapabilities || [];
  const partnerL1 = new Set([...splitCapabilityNames(capabilities), ...subs.map((item) => item.parent)]);
  if (selectedL1.some((value) => partnerL1.has(value))) return true;
  const partnerSubPairs = new Set(subs.map((item) => `${item.parent}/${item.name}`));
  return selectedSubPairs.some((pair) => partnerSubPairs.has(pair));
}

export function PartnerGroupedCapabilityList({
  capabilities,
  subCapabilities,
  emptyText = "未完善",
}: {
  capabilities: string | null | undefined;
  subCapabilities?: SubCapabilityItem[] | null;
  emptyText?: string;
}) {
  const groups = groupPartnerCapabilities(capabilities, subCapabilities);
  if (!groups.length) return <p className="partner-tag-empty">{emptyText}</p>;
  return (
    <ul className="partner-capability-summary-list" aria-label="正式能力标签" role="list">
      {groups.map((group) => (
        <li key={group.parent} className="partner-capability-summary-item">
          <span className="partner-capability-l1-badge">{group.parent}</span>
          {group.children.length > 0 && (
            <span className="partner-capability-l2-inline">
              {group.children.map((child) => (
                <span key={child} className="partner-capability-l2-chip">{child}</span>
              ))}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

type Props = {
  tree: CapabilityCategoryNode[];
  capabilities: string;
  subCapabilities: SubCapabilityItem[];
  disabled?: boolean;
  tagError?: string;
  onRetryTags?: () => void;
  onChange: (capabilities: string, subCapabilities: SubCapabilityItem[]) => void;
};

export function PartnerCapabilityFields({
  tree,
  capabilities,
  subCapabilities,
  disabled = false,
  tagError,
  onRetryTags,
  onChange,
}: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const selectedL1 = splitCapabilityNames(capabilities);
  const selectedL1Set = new Set(selectedL1);
  const subs = subCapabilities || [];

  const treeL1Names = new Set(tree.flatMap((cat) => cat.tags.map((tag) => tag.name)));
  const treeL2Keys = new Set(
    tree.flatMap((cat) =>
      cat.tags.flatMap((tag) => tag.children.map((child) => `${tag.name}\0${child.name}`)),
    ),
  );
  const legacyL1 = selectedL1.filter((name) => !treeL1Names.has(name));
  const legacySubs = subs.filter((item) => !treeL2Keys.has(`${item.parent}\0${item.name}`));

  function toggleL1(l1Name: string, checked: boolean) {
    const nextL1 = checked
      ? [...new Set([...selectedL1, l1Name])]
      : selectedL1.filter((name) => name !== l1Name);
    const nextSubs = checked ? subs : subs.filter((item) => item.parent !== l1Name);
    onChange(nextL1.join(","), nextSubs);
  }

  function toggleL2(parentName: string, childName: string, checked: boolean) {
    const nextL1 = checked ? [...new Set([...selectedL1, parentName])] : selectedL1;
    const exists = subs.some((item) => item.parent === parentName && item.name === childName);
    let nextSubs = subs;
    if (checked && !exists) {
      nextSubs = [...subs, { parent: parentName, name: childName }];
    } else if (!checked && exists) {
      nextSubs = subs.filter((item) => !(item.parent === parentName && item.name === childName));
    }
    onChange(nextL1.join(","), nextSubs);
  }

  function isExpanded(l1: CapabilityL1Tag) {
    if (expanded[l1.id] !== undefined) return expanded[l1.id];
    return subs.some((item) => item.parent === l1.name);
  }

  return (
    <fieldset className="classification-options partner-capability-options form-span-two" disabled={disabled}>
      <legend>能力标签（一二级多选）</legend>
      <div className="capability-tree-picker">
        {tree.map((category) => (
          <div key={category.id || category.name} className="capability-category-block">
            <div className="capability-category-title">{category.name}</div>
            <div className="capability-l1-grid">
              {category.tags.map((l1) => {
                const l1Checked = selectedL1Set.has(l1.name);
                const selectedChildrenCount = subs.filter((item) => item.parent === l1.name).length;
                const open = isExpanded(l1);
                return (
                  <div key={l1.id} className={`capability-l1-card ${l1Checked ? "is-selected" : ""}`}>
                    <div className="capability-l1-header">
                      <label className="capability-l1-label">
                        <input
                          type="checkbox"
                          checked={l1Checked}
                          onChange={(e) => toggleL1(l1.name, e.target.checked)}
                        />
                        <span>{l1.name}</span>
                      </label>
                      {l1.children.length > 0 && (
                        <button
                          type="button"
                          className="capability-expand-btn"
                          onClick={() => setExpanded((prev) => ({ ...prev, [l1.id]: !open }))}
                        >
                          {open ? "收起" : "细分"}
                          {selectedChildrenCount > 0
                            ? ` (${selectedChildrenCount}/${l1.children.length})`
                            : ` (${l1.children.length})`}
                        </button>
                      )}
                    </div>
                    {open && l1.children.length > 0 && (
                      <div className="capability-l2-list">
                        {l1.children.map((child) => {
                          const childChecked = subs.some(
                            (item) => item.parent === l1.name && item.name === child.name,
                          );
                          return (
                            <label key={child.id} className="capability-l2-label">
                              <input
                                type="checkbox"
                                checked={childChecked}
                                onChange={(e) => toggleL2(l1.name, child.name, e.target.checked)}
                              />
                              <span>{child.name}</span>
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        {(legacyL1.length > 0 || legacySubs.length > 0) && (
          <div className="capability-category-block">
            <div className="capability-category-title">其他 / 历史保留标签</div>
            <div className="capability-legacy-list">
              {legacyL1.map((name) => (
                <label key={`legacy-l1-${name}`}>
                  <input
                    type="checkbox"
                    checked
                    onChange={(e) => toggleL1(name, e.target.checked)}
                  />
                  <span>{name}</span>
                </label>
              ))}
              {legacySubs.map((item) => (
                <label key={`legacy-l2-${item.parent}-${item.name}`}>
                  <input
                    type="checkbox"
                    checked
                    onChange={(e) => toggleL2(item.parent, item.name, e.target.checked)}
                  />
                  <span>{item.parent} / {item.name}</span>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>

      {tagError && (
        <p className="error-text" role="alert">
          {tagError}{" "}
          {onRetryTags && (
            <button type="button" className="secondary-btn" onClick={onRetryTags}>
              重试
            </button>
          )}
        </p>
      )}
      <p className="muted">
        已选一级 {selectedL1.length} 项、二级 {subs.length} 项（勾选二级将自动勾选所属一级）；新增可选标签请前往
        <Link href="/admin/tags">能力标签管理</Link>。
      </p>
    </fieldset>
  );
}
