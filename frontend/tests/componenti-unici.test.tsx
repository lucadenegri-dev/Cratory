import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { PageLayout } from "../components/page-layout";

describe("componenti condivisi in una copia sola", () => {
  for (const c of ["page-layout", "ui", "path-picker-button"]) {
    it(`components/organize/${c}.tsx è stato rimosso`, () => {
      expect(existsSync(resolve(__dirname, `../components/organize/${c}.tsx`))).toBe(false);
    });
  }

  it("rende lo slot action, che veniva da Cratory", () => {
    render(<PageLayout title="T" action={<button>Azione</button>}>x</PageLayout>);
    expect(screen.getByRole("button", { name: "Azione" })).toBeTruthy();
  });

  it("rende lo slot guide, che veniva da Organize", () => {
    render(<PageLayout title="T" guide={<p>Come si usa</p>}>x</PageLayout>);
    expect(screen.getByText("Come si usa")).toBeTruthy();
  });

  it("apre la colonna marginale anche con la sola guide", () => {
    const { container } = render(<PageLayout title="T" guide={<p>G</p>}>x</PageLayout>);
    expect(container.querySelector("aside")).not.toBeNull();
  });

  it("non apre la colonna marginale se non c'è né marginalia né guide", () => {
    const { container } = render(<PageLayout title="T">x</PageLayout>);
    expect(container.querySelector("aside")).toBeNull();
  });
});
