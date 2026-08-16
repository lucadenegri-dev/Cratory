import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PageLayout } from "@/components/page-layout";

/* La colonna marginale (240px) viene pubblicata in --content-aside-width: la
   barra player la usa per fermarsi al bordo della colonna invece di passarci
   sotto. Senza colonna la var resta 0px, e torna 0px allo smontaggio. */
describe("PageLayout: --content-aside-width", () => {
  afterEach(cleanup);

  const readVar = () => document.documentElement.style.getPropertyValue("--content-aside-width");

  it("con marginalia pubblica 240px; allo smontaggio torna 0px", () => {
    const { unmount } = render(
      <PageLayout title="T" marginalia={<div>filtri</div>}>
        <div>corpo</div>
      </PageLayout>,
    );
    expect(readVar()).toBe("240px");
    unmount();
    expect(readVar()).toBe("0px");
  });

  it("senza marginalia né guide pubblica 0px", () => {
    render(
      <PageLayout title="T">
        <div>corpo</div>
      </PageLayout>,
    );
    expect(readVar()).toBe("0px");
  });

  it("con la sola guide pubblica comunque 240px (la colonna si apre)", () => {
    render(
      <PageLayout title="T" guide={<p>istruzioni</p>}>
        <div>corpo</div>
      </PageLayout>,
    );
    expect(readVar()).toBe("240px");
  });
});
