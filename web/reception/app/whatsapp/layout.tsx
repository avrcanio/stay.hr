import { WhatsAppSubNav } from "@/app/whatsapp/_components/WhatsAppSubNav";

export default function WhatsAppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <WhatsAppSubNav />
      {children}
    </div>
  );
}
