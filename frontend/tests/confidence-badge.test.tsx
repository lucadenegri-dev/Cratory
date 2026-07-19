import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ConfidenceBadge } from "@/components/confidence-badge";

describe("confidence badge", () => {
  afterEach(cleanup);

  it("marca come dubbia una voce sotto la soglia", () => {
    render(<ConfidenceBadge confidence={45} />);
    expect(screen.getByText("DUBBIA")).toBeTruthy();
  });

  it("niente badge con confidence alta, legacy o assente", () => {
    render(
      <>
        <ConfidenceBadge confidence={90} />
        <ConfidenceBadge confidence={80} />
        <ConfidenceBadge confidence={null} />
      </>,
    );
    expect(screen.queryByText("DUBBIA")).toBeNull();
  });
});
