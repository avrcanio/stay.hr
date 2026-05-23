import type { CalendarBlock } from "@/lib/types";

/** Blocks linked to a reservation are shown on the reservation card, not separately. */
export function standaloneBlocks(blocks: CalendarBlock[]): CalendarBlock[] {
  return blocks.filter((block) => block.reservation_id == null);
}

export function reservationHasChannelBlock(
  reservationId: number,
  blocks: CalendarBlock[],
): boolean {
  return blocks.some((block) => block.reservation_id === reservationId);
}
