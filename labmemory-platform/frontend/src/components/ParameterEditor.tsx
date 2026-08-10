import { useState } from "react";

export interface ParamRow {
  name: string;
  value: string;
  unit?: string;
}

interface ParameterEditorProps {
  rows: ParamRow[];
  onChange: (rows: ParamRow[]) => void;
  /** params=三列（名称/值/单位）；kv=两列（键/值） */
  mode?: "params" | "kv";
  namePlaceholder?: string;
  valuePlaceholder?: string;
  emptyHint?: string;
  addLabel?: string;
}

export default function ParameterEditor({
  rows,
  onChange,
  mode = "params",
  namePlaceholder = "参数名",
  valuePlaceholder = "值",
  emptyHint,
  addLabel,
}: ParameterEditorProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [jsonDraft, setJsonDraft] = useState("");
  const [jsonError, setJsonError] = useState("");

  const updateRow = (i: number, patch: Partial<ParamRow>) => {
    onChange(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  };

  const removeRow = (i: number) => {
    onChange(rows.filter((_, idx) => idx !== i));
  };

  const addRow = () => {
    onChange([...rows, { name: "", value: "", unit: mode === "params" ? "" : undefined }]);
  };

  const openAdvanced = () => {
    setJsonDraft(JSON.stringify(rows, null, 2));
    setJsonError("");
    setAdvancedOpen(true);
  };

  const applyJson = () => {
    try {
      const parsed = JSON.parse(jsonDraft);
      if (!Array.isArray(parsed)) throw new Error("必须是数组");
      onChange(
        parsed.map((r) => ({
          name: String(r?.name ?? ""),
          value: String(r?.value ?? ""),
          unit: r?.unit != null ? String(r.unit) : undefined,
        }))
      );
      setJsonError("");
      setAdvancedOpen(false);
    } catch {
      setJsonError("JSON 格式错误：必须是 [{name, value, unit}] 数组");
    }
  };

  const gridCols = mode === "params" ? "1fr 1fr 84px 36px" : "1fr 1fr 36px";

  const DelIcon = (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  );

  return (
    <div>
      <div className="pe-table">
        {/* 表头 */}
        <div className="pe-header" style={{ gridTemplateColumns: gridCols }}>
          <span>{namePlaceholder}</span>
          <span>{valuePlaceholder}</span>
          {mode === "params" && <span>单位</span>}
          <span />
        </div>

        {/* 行编辑 */}
        {rows.length === 0 ? (
          <div className="pe-empty">
            {emptyHint || "暂无参数，点击下方「+ 添加」新增一行"}
          </div>
        ) : (
          rows.map((r, i) => (
            <div
              key={i}
              className="pe-row"
              style={{ gridTemplateColumns: gridCols }}
            >
              <input
                className="pe-input mono"
                value={r.name}
                onChange={(e) => updateRow(i, { name: e.target.value })}
                placeholder={namePlaceholder}
              />
              <input
                className="pe-input"
                value={r.value}
                onChange={(e) => updateRow(i, { value: e.target.value })}
                placeholder={valuePlaceholder}
              />
              {mode === "params" && (
                <input
                  className="pe-input"
                  value={r.unit ?? ""}
                  onChange={(e) => updateRow(i, { unit: e.target.value })}
                  placeholder="如 ℃"
                />
              )}
              <button
                className="pe-del"
                title="删除此行"
                onClick={() => removeRow(i)}
              >
                {DelIcon}
              </button>
            </div>
          ))
        )}
      </div>

      <div className="pe-actions">
        <button className="pe-add" onClick={addRow}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          {addLabel || (mode === "params" ? "添加参数" : "添加项")}
        </button>
        <button className="btn sm" onClick={openAdvanced}>
          高级 JSON
        </button>
      </div>

      {advancedOpen && (
        <div className="pe-advanced">
          <div className="pe-advanced-head">
            <span>高级 JSON 编辑</span>
            <span className="text-xs muted">
              {mode === "params"
                ? '[{"name":"温度","value":"70","unit":"℃"}]'
                : '[{"name":"转化率","value":"78%"}]'}
            </span>
          </div>
          <textarea
            value={jsonDraft}
            onChange={(e) => setJsonDraft(e.target.value)}
          />
          {jsonError && <div className="text-xs text-red-500 mt-1.5">{jsonError}</div>}
          <div className="flex justify-end gap-2 mt-2.5">
            <button className="btn sm" onClick={() => setAdvancedOpen(false)}>
              收起
            </button>
            <button className="btn sm primary" onClick={applyJson}>
              应用
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
