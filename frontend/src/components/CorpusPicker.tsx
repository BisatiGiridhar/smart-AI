import { useCorpora } from "../lib/hooks";
import { Field, Select, SyntheticNotice } from "./ui";

export function CorpusPicker({ value, onChange, label = "Corpus" }: { value: string; onChange: (v: string) => void; label?: string }) {
  const { options, syntheticLabel } = useCorpora();
  return (
    <div className="space-y-2">
      <Field label={label} hint="Synthetic research records and genuine candidates are never mixed in one search.">
        <Select value={value} onChange={(e) => onChange(e.target.value)} options={options} />
      </Field>
      {value.startsWith("dataset:") && <SyntheticNotice label={syntheticLabel} />}
    </div>
  );
}
