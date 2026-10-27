import { normalizeOrderTimeline, orderTimelineLabel } from "./orderTimeline.js";

export default function OrderTimeline({ items, shipment }) {
  const timeline = normalizeOrderTimeline(items);
  if (!timeline.length) return <p className="order-timeline-empty">No order updates have been recorded yet.</p>;
  return <ol className="order-timeline">
    {timeline.map((item) => <li key={item.id}>
      <span className="order-timeline-marker" aria-hidden="true" />
      <div className="order-timeline-content">
        <strong>{orderTimelineLabel(item.status)}</strong>
        <time dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleString()}</time>
        {item.status === "shipped" && shipment?.trackingNumber
          ? <p>Tracking number: <strong>{shipment.trackingNumber}</strong>{shipment.carrier ? ` · ${shipment.carrier}` : ""}</p>
          : null}
        {item.note ? <p>{item.note}</p> : null}
      </div>
    </li>)}
  </ol>;
}
