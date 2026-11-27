import type { Metadata } from "next";
import { AstrologerWorkspace } from "@/components/astrologer/AstrologerWorkspace";

export const metadata: Metadata = {
  title: "Astrologer Workspace | Kundali",
  robots: { index: false, follow: false },
};

export default function AstrologerDashboard() {
  return <AstrologerWorkspace />;
}
