import enMessages from "@/i18n/en.json";
import neMessages from "@/i18n/ne.json";
import { UserChartWorkspace, type WorkspaceMessages } from "@/components/user/UserChartWorkspace";

export default function UserDashboard() {
  const messagesByLocale: { en: WorkspaceMessages; ne: WorkspaceMessages } = {
    en: enMessages.userWorkspace,
    ne: neMessages.userWorkspace,
  };

  return <UserChartWorkspace messagesByLocale={messagesByLocale} />;
}
