import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getBambuClient, getSettings } from "@/lib/data";
import { BambuConnect } from "./bambu-connect";
import { TrackerSettings } from "./tracker-settings";

async function listDevices(connected: boolean) {
  if (!connected) return [];
  try {
    const devices = await (await getBambuClient()).getDevices();
    return devices.map((d) => ({ id: d.dev_id, name: d.name || d.dev_product_name || d.dev_id }));
  } catch {
    return []; // token expired or Bambu unreachable; fall back to a text field
  }
}

export default async function SettingsPage() {
  const settings = await getSettings();
  const devices = await listDevices(settings.connected);

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>

      <Card>
        <CardHeader>
          <CardTitle>Bambu Cloud</CardTitle>
          <CardDescription>Connect your Bambu Lab account to sync print history.</CardDescription>
        </CardHeader>
        <CardContent>
          <BambuConnect
            connected={settings.connected}
            email={settings.bambu_email}
            region={settings.bambu_region}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Tracker</CardTitle>
          <CardDescription>
            Use more than one slot if you print from an AMS Lite; multi-colour jobs are split per slot.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <TrackerSettings slotCount={settings.slot_count} deviceId={settings.device_id} devices={devices} />
        </CardContent>
      </Card>
    </div>
  );
}
