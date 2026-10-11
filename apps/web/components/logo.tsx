import Link from "next/link";

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 text-sm font-semibold tracking-tight text-fg">
      <span className="relative inline-flex h-5 w-5 items-center justify-center rounded-md border border-line-strong bg-raised">
        <span className="h-2 w-2 rounded-full border-[1.5px] border-brand" />
      </span>
      RepoLens
    </Link>
  );
}
