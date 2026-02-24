# Generic nav_components Display Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace hardcoded `'Carried interest accrued'` lookups in node components with a generic `displayNavComponents` array on `FundViewContext`, so views control which NAV waterfall line items appear on node cards.

**Architecture:** Add a `displayNavComponents: string[]` field to `FundViewContext`. Each view provider (`CrmEntityView`, `FundView`, `LppaFundView`) sets its own list. Node components iterate this list instead of hardcoding specific key lookups. PartnersTable/PartnersOverTimeTable replace the `isGPEntity` carry guard with context-driven display.

**Tech Stack:** React 17, TypeScript, Jest, React Testing Library

**Branch:** `gpe-276.cartian.entity_map_carry_conditional_display` (existing)

**Test command:** `rush test --only=@carta/entity-map`

---

### Task 1: Add `displayNavComponents` to FundViewContext

**Files:**
- Modify: `apps/fund-admin/entity-map/src/core/contexts/FundViewContext.tsx`
- Modify: `apps/fund-admin/entity-map/src/core/contexts/__tests__/FundViewContext.test.tsx`

**Step 1: Write the failing test**

In `FundViewContext.test.tsx`, update the `fundViewContextValue` fixture and the `useFundViewContext` assertion to include `displayNavComponents`:

```typescript
const fundViewContextValue: FundViewContextType = {
    endDate: mockEndDate,
    effectiveDate: mockEffectiveDate,
    layoutDirection: mockLayoutDirection,
    setLayoutDirection: mockSetLayoutDirection,
    currency: 'USD',
    displayNavComponents: ['Carried interest accrued'],
};
```

And in the `'should return context values when used within provider'` test:

```typescript
expect(result.current).toEqual({
    endDate: mockEndDate,
    effectiveDate: mockEffectiveDate,
    layoutDirection: mockLayoutDirection,
    setLayoutDirection: mockSetLayoutDirection,
    currency: 'USD',
    displayNavComponents: ['Carried interest accrued'],
});
```

**Step 2: Run test to verify it fails**

Run: `rush test --only=@carta/entity-map -- --testPathPattern="FundViewContext" --verbose`
Expected: FAIL — `displayNavComponents` not in type / not in context value

**Step 3: Implement the change**

In `FundViewContext.tsx`:

Add `displayNavComponents: string[]` to `FundViewContextType`:

```typescript
export type FundViewContextType = {
    endDate: string;
    effectiveDate: string;
    layoutDirection: LayoutDirection;
    setLayoutDirection: (direction: LayoutDirection) => void;
    currency: Ink.CurrencyProps['code'];
    displayNavComponents: string[];
};
```

Add `displayNavComponents` to the `useMemo` value and dependency array in `FundViewContextProvider`.

**Step 4: Run test to verify it passes**

Run: `rush test --only=@carta/entity-map -- --testPathPattern="FundViewContext" --verbose`
Expected: PASS

**Step 5: Commit**

```
feat(entity-map): add displayNavComponents to FundViewContext
```

---

### Task 2: Update test utilities to provide `displayNavComponents`

**Files:**
- Modify: `apps/fund-admin/entity-map/src/core/components/test-utils/renderWithContexts.tsx`
- Modify: `apps/fund-admin/entity-map/src/core/components/test-utils/renderWithLppaContexts.tsx`

**Step 1: Update `renderWithContexts`**

Add `displayNavComponents` to `ContextProviderProps` type and the `customRender` function:

```typescript
type ContextProviderProps = {
    // ... existing props ...
    displayNavComponents?: string[];
    // ...
};
```

Default to `['Carried interest accrued']` in the destructured params (matches current behavior where carry is always shown in Fund Admin tests):

```typescript
displayNavComponents = ['Carried interest accrued'],
```

Pass to `FundViewContextProvider`:

```typescript
<FundViewContextProvider
    endDate={endDate}
    effectiveDate={effectiveDate}
    layoutDirection={layoutDirection}
    setLayoutDirection={setLayoutDirection}
    currency={currency}
    displayNavComponents={displayNavComponents}
>
```

**Step 2: Update `renderWithLppaContexts`**

Same pattern. Default to `[]` (LPPA doesn't show carry on node cards currently).

```typescript
<FundViewContextProvider
    endDate={endDate}
    effectiveDate=""
    layoutDirection={layoutDirection}
    setLayoutDirection={setLayoutDirection}
    currency={currency || 'USD'}
    displayNavComponents={[]}
>
```

**Step 3: Run the full test suite to confirm nothing breaks**

Run: `rush test --only=@carta/entity-map`
Expected: All existing tests should still pass (TypeScript will flag any missing props)

**Step 4: Commit**

```
chore(entity-map): plumb displayNavComponents through test utilities
```

---

### Task 3: Wire up view providers

**Files:**
- Modify: `apps/fund-admin/entity-map/src/core/components/CrmEntityView/CrmEntityView.tsx`
- Modify: `apps/fund-admin/entity-map/src/core/components/FundView/FundView.tsx`
- Modify: `apps/fund-admin/entity-map/src/core/lppa/LppaFundView.tsx`

**Step 1: Add constants and pass to providers**

In each file, define a stable constant outside the component and pass it to `FundViewContextProvider`.

`CrmEntityView.tsx`:
```typescript
const CRM_DISPLAY_NAV_COMPONENTS = ['Carried interest accrued'];

// In the JSX:
<FundViewContextProvider
    displayNavComponents={CRM_DISPLAY_NAV_COMPONENTS}
    // ... existing props ...
>
```

`FundView.tsx`:
```typescript
const FUND_VIEW_DISPLAY_NAV_COMPONENTS = ['Carried interest accrued'];

// In the JSX:
<FundViewContextProvider
    displayNavComponents={FUND_VIEW_DISPLAY_NAV_COMPONENTS}
    // ... existing props ...
>
```

`LppaFundView.tsx`:
```typescript
const LPPA_DISPLAY_NAV_COMPONENTS: string[] = [];

// In the JSX:
<FundViewContextProvider
    displayNavComponents={LPPA_DISPLAY_NAV_COMPONENTS}
    // ... existing props ...
>
```

**Step 2: Also update any storybook files that use `FundViewContextProvider`**

Check: `apps/fund-admin/entity-map/src/core/components/FundView/__storybook__/LayoutToggle.stories.tsx`

Pass `displayNavComponents={[]}` (or whatever makes sense for the story).

**Step 3: Run type check**

Run: `rush tsc --only=@carta/entity-map`
Expected: PASS — no missing prop errors

**Step 4: Commit**

```
feat(entity-map): configure displayNavComponents per view provider
```

---

### Task 4: Refactor `AsOfDateGPEntityNode` to use `displayNavComponents`

**Files:**
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/as-of-date/AsOfDateGPEntityNode.tsx`
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/as-of-date/__tests__/AsOfDateGPEntityNode.test.tsx`

**Step 1: Write the failing test — context controls visibility**

Add a new test that passes `displayNavComponents: []` to `renderWithContexts` and asserts carry is hidden even when the key exists in data:

```typescript
it('hides nav component metrics when not in displayNavComponents', () => {
    mockZoom(0.75);
    renderWithContexts(
        <AsOfDateGPEntityNode
            id="gp-entity-node"
            data={mockGPEntityNodeData}  // has carry in nav_components
            type="as_of_date_gp_entity"
            isConnectable={false}
            selected={false}
            dragging={false}
            draggable={false}
            selectable={false}
            deletable={false}
            zIndex={1}
            positionAbsoluteX={0}
            positionAbsoluteY={0}
        />,
        { displayNavComponents: [] },
    );

    const gpEntityNode = screen.getByTestId('as-of-date-gp-entity-node');
    expect(gpEntityNode).not.toHaveTextContent('Carried interest accrued');
    expect(gpEntityNode).toHaveTextContent('NAV');
});
```

**Step 2: Run test to verify it fails**

Run: `rush test --only=@carta/entity-map -- --testPathPattern="AsOfDateGPEntityNode" --verbose`
Expected: FAIL — carry still shows because component hardcodes the lookup

**Step 3: Refactor the component**

Replace the hardcoded carry lookup with a generic iteration:

```typescript
export const AsOfDateGPEntityNode = React.memo(
    ({ id, data }: NodeProps<AsOfDateGPEntityNodeType>) => {
        const { closeFloatingTile } = useFloatingTileContext();
        const { currency, displayNavComponents } = useFundViewContext();

        const isCommitmentHidden = BigNumber(data.metrics.end_metrics.commitment).isZero();

        return (
            <BaseNodeWithFloatingTile
                id={id}
                testId="as-of-date-gp-entity-node"
                tileContent={<AsOfDateGPEntityNodeTile onClose={closeFloatingTile} data={data} />}
            >
                <NodeWrapper nodeType={data.nodeType} status={data.status}>
                    <SourceHandle top="85%" />
                    <NodeContent
                        label={data.label}
                        collapsedView={
                            <CollapsedMetricView
                                label="NAV"
                                value={data.nav_metrics.ending_nav}
                                code={currency}
                            />
                        }
                        expandedView={
                            <Ink.VStack spacing="small">
                                {displayNavComponents.map(key => {
                                    const value = data.nav_metrics.nav_components[key];
                                    return value !== undefined ? (
                                        <CollapsedMetricView
                                            key={key}
                                            label={key}
                                            value={value}
                                            code={currency}
                                        />
                                    ) : null;
                                })}
                                {!isCommitmentHidden && (
                                    <CollapsedMetricView
                                        label="Commitment"
                                        value={data.metrics.end_metrics.commitment}
                                        code={currency}
                                    />
                                )}
                                <CollapsedMetricView
                                    label="NAV"
                                    value={data.nav_metrics.ending_nav}
                                    code={currency}
                                />
                            </Ink.VStack>
                        }
                    />
                    <TargetHandle top="40%" />
                </NodeWrapper>
            </BaseNodeWithFloatingTile>
        );
    },
);
```

**Step 4: Run tests to verify all pass**

Run: `rush test --only=@carta/entity-map -- --testPathPattern="AsOfDateGPEntityNode" --verbose`
Expected: PASS — all existing tests still pass (test utility defaults to `['Carried interest accrued']`), new test passes

**Step 5: Commit**

```
refactor(entity-map): AsOfDateGPEntityNode uses displayNavComponents
```

---

### Task 5: Refactor `JournalGPEntityNode` to use `displayNavComponents`

**Files:**
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/journal/JournalGPEntityNode.tsx`
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/journal/__tests__/JournalGPEntityNode.test.tsx`

**Step 1: Write the failing test**

Same pattern as Task 4 — add a test with `displayNavComponents: []`:

```typescript
it('hides nav component metrics when not in displayNavComponents', () => {
    mockZoom(0.75);
    renderWithContexts(
        <JournalGPEntityNode
            id="gp-entity-node"
            data={mockJournalGPEntityNodeData}
            type="journal_gp_entity"
            isConnectable={false}
            selected={false}
            dragging={false}
            draggable={false}
            selectable={false}
            deletable={false}
            zIndex={1}
            positionAbsoluteX={0}
            positionAbsoluteY={0}
        />,
        { displayNavComponents: [] },
    );

    const gpEntityNode = screen.getByTestId('journal-gp-entity-node');
    expect(gpEntityNode).not.toHaveTextContent('Carried interest accrued');
    expect(gpEntityNode).toHaveTextContent('NAV');
});
```

**Step 2: Run test to verify it fails**

Run: `rush test --only=@carta/entity-map -- --testPathPattern="JournalGPEntityNode" --verbose`
Expected: FAIL

**Step 3: Refactor the component**

Replace hardcoded carry lookups with generic iteration. Journal nodes need both `end` and `change`:

```typescript
export const JournalGPEntityNode = React.memo(
    ({ id, data }: NodeProps<JournalGPEntityNodeType>) => {
        const { closeFloatingTile } = useFloatingTileContext();
        const { currency, displayNavComponents } = useFundViewContext();

        const isCommitmentHidden = BigNumber(data.metrics.end_metrics.commitment).isZero();

        return (
            <BaseNodeWithFloatingTile
                id={id}
                testId="journal-gp-entity-node"
                tileContent={<JournalGPEntityNodeTile onClose={closeFloatingTile} data={data} />}
                enabled={data.state === 'participating'}
            >
                <NodeWrapper nodeType={data.nodeType} state={data.state}>
                    <SourceHandle top="85%" />
                    <NodeContent
                        label={data.label}
                        state={data.state}
                        collapsedView={
                            <CollapsedMetricView
                                label="NAV"
                                value={data.nav_metrics.end.ending_nav}
                                code={currency}
                            />
                        }
                        expandedView={
                            <Ink.VStack spacing="small">
                                {displayNavComponents.map(key => {
                                    const value = data.nav_metrics.end.nav_components[key];
                                    const change = data.nav_metrics.change.nav_components[key];
                                    return value !== undefined ? (
                                        <CollapsedMetricView
                                            key={key}
                                            label={key}
                                            value={value}
                                            change={change}
                                            code={currency}
                                        />
                                    ) : null;
                                })}
                                {!isCommitmentHidden && (
                                    <CollapsedMetricView
                                        label="Commitment"
                                        value={data.metrics.end_metrics.commitment}
                                        change="0"
                                        code={currency}
                                    />
                                )}
                                <CollapsedMetricView
                                    label="NAV"
                                    value={data.nav_metrics.end.ending_nav}
                                    change={data.nav_metrics.change.ending_nav}
                                    code={currency}
                                />
                            </Ink.VStack>
                        }
                    />
                    <TargetHandle top="40%" />
                </NodeWrapper>
            </BaseNodeWithFloatingTile>
        );
    },
);
```

**Step 4: Run tests**

Run: `rush test --only=@carta/entity-map -- --testPathPattern="JournalGPEntityNode" --verbose`
Expected: PASS

**Step 5: Commit**

```
refactor(entity-map): JournalGPEntityNode uses displayNavComponents
```

---

### Task 6: Refactor `IndividualPortfolioNode` to use `displayNavComponents`

**Files:**
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/individual-portfolio/IndividualPortfolioNode.tsx`
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/individual-portfolio/__tests__/IndividualPortfolioNode.test.tsx`

**Step 1: Write the failing test**

```typescript
it('hides nav component metrics when not in displayNavComponents', () => {
    mockZoom(0.75);
    renderWithContexts(
        <IndividualPortfolioNode
            id="individual-portfolio-node"
            data={baseData}  // has carry in nav_components
            type="individual_portfolio"
            isConnectable={false}
            selected={false}
            dragging={false}
            draggable={false}
            selectable={false}
            deletable={false}
            zIndex={1}
            positionAbsoluteX={0}
            positionAbsoluteY={0}
        />,
        { displayNavComponents: [] },
    );

    const node = screen.getByTestId('individual-portfolio-node');
    expect(node).not.toHaveTextContent('Carried interest accrued');
    expect(node).toHaveTextContent('NAV');
});
```

**Step 2: Run test to verify it fails**

Run: `rush test --only=@carta/entity-map -- --testPathPattern="IndividualPortfolioNode" --verbose`
Expected: FAIL

**Step 3: Refactor the component**

Same pattern as AsOfDateGPEntityNode (AsOfDate-style `nav_metrics`):

```typescript
export const IndividualPortfolioNode = React.memo(
    ({ id, data }: NodeProps<IndividualPortfolioNodeType>) => {
        const { closeFloatingTile } = useFloatingTileContext();
        const { currency, displayNavComponents } = useFundViewContext();

        return (
            <BaseNodeWithFloatingTile
                id={id}
                testId="individual-portfolio-node"
                tileContent={
                    <IndividualPortfolioNodeTile onClose={closeFloatingTile} data={data} />
                }
            >
                <NodeWrapper nodeType={data.nodeType}>
                    <SourceHandle top="85%" />
                    <NodeContent
                        label={data.label}
                        collapsedView={
                            <CollapsedMetricView
                                label="NAV"
                                value={data.nav_metrics.ending_nav}
                                code={currency}
                            />
                        }
                        expandedView={
                            <Ink.VStack spacing="small">
                                {displayNavComponents.map(key => {
                                    const value = data.nav_metrics.nav_components[key];
                                    return value !== undefined ? (
                                        <CollapsedMetricView
                                            key={key}
                                            label={key}
                                            value={value}
                                            code={currency}
                                        />
                                    ) : null;
                                })}
                                <CollapsedMetricView
                                    label="Commitment"
                                    value={data.metrics.end_metrics.commitment}
                                    code={currency}
                                />
                                <CollapsedMetricView
                                    label="Called capital"
                                    value={data.metrics.end_metrics.called_capital}
                                    code={currency}
                                />
                                <CollapsedMetricView
                                    label="NAV"
                                    value={data.nav_metrics.ending_nav}
                                    code={currency}
                                />
                            </Ink.VStack>
                        }
                    />
                    <TargetHandle top="40%" />
                </NodeWrapper>
            </BaseNodeWithFloatingTile>
        );
    },
);
```

**Step 4: Run tests**

Run: `rush test --only=@carta/entity-map -- --testPathPattern="IndividualPortfolioNode" --verbose`
Expected: PASS

**Step 5: Commit**

```
refactor(entity-map): IndividualPortfolioNode uses displayNavComponents
```

---

### Task 7: Refactor `PartnersTable` to use `displayNavComponents`

The `PartnersTable` currently uses `isGPEntity` to conditionally show the carry column. Replace this with context-driven display: show a column for each `displayNavComponents` key.

**Files:**
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/PartnersTable.tsx`
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/__tests__/PartnersTable.test.tsx`
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/as-of-date/AsOfDateGpEntityNodeTile.tsx`

**Step 1: Write the failing test**

The `PartnersTable` currently uses `isGPEntity` and takes `carriedInterestAccrued` in `totals`. The new version reads `displayNavComponents` from context. Wrap the existing `PartnersTable` test renders with `renderWithContexts` (or a wrapper providing `FundViewContext`) so the component can access context.

Add a test that renders with `displayNavComponents: []` and asserts the carry column is absent:

```typescript
it('hides nav component columns when displayNavComponents is empty', () => {
    renderWithContexts(
        <PartnersTable
            partners={mockPartnersFromFundApiV2}
            totals={{ commitment: '123', nav: '456' }}
        />,
        { displayNavComponents: [] },
    );

    const columnHeaders = screen.getAllByRole('columnheader');
    expect(columnHeaders).toHaveLength(3);
    expect(columnHeaders[0]).toHaveTextContent('Partner');
    expect(columnHeaders[1]).toHaveTextContent('Commitment');
    expect(columnHeaders[2]).toHaveTextContent('NAV');
});
```

**Step 2: Run test to verify it fails**

Run: `rush test --only=@carta/entity-map -- --testPathPattern="PartnersTable" --verbose`
Expected: FAIL — `isGPEntity` still controls the column

**Step 3: Refactor `PartnersTable`**

Remove the `isGPEntity` prop and `carriedInterestAccrued` from `totals`. Read `displayNavComponents` from context. For each key in the list, render a column if the key exists in partner data:

```typescript
import { useFundViewContext } from 'core/contexts/FundViewContext';

type PartnersTableProps = {
    partners: PartnerChildNodeFromFundApi[];
    totals: {
        commitment: string;
        nav: string;
        navComponents?: Record<string, string>;
    };
    currency?: Ink.CurrencyProps['code'];
};

export const PartnersTable = ({ partners, totals, currency }: PartnersTableProps) => {
    const { displayNavComponents } = useFundViewContext();
    const isGPEntity = displayNavComponents.length > 0;
    // ... rest of component iterates displayNavComponents for columns
};
```

Wait — the `isGPEntity` flag is also used for the empty state text ("members" vs "partners") and the `Member` vs `Partner` column header. Those are labeling concerns, not metric concerns. Keep `isGPEntity` for labeling but decouple it from the carry column.

Revised approach: keep `isGPEntity` for label text only. Replace the carry column logic with iteration over `displayNavComponents`:

```typescript
type PartnersTableProps = {
    partners: PartnerChildNodeFromFundApi[];
    totals: {
        commitment: string;
        nav: string;
        navComponents?: Record<string, string>;
    };
    isGPEntity: boolean;
    currency?: Ink.CurrencyProps['code'];
};

export const PartnersTable = ({ partners, totals, isGPEntity, currency }: PartnersTableProps) => {
    const { displayNavComponents } = useFundViewContext();
    const sortedPartners = React.useMemo(
        () => [...partners].sort((a, b) => a.name.localeCompare(b.name)),
        [partners],
    );

    if (partners.length === 0) {
        return (
            <Ink.EmptyState
                type={isGPEntity ? 'block' : 'page'}
                icon="notfound"
                text={`No ${isGPEntity ? 'members' : 'partners'} to display.`}
            />
        );
    }

    return (
        <Ink.NewTable height="400px" density="high" data-testid="partners-table">
            <Ink.NewTable.Head>
                <Ink.NewTable.Row>
                    <Ink.NewTable.HeadCell width="40%">
                        {isGPEntity ? 'Member' : 'Partner'}
                    </Ink.NewTable.HeadCell>
                    {displayNavComponents.map(key => (
                        <Ink.NewTable.HeadCell key={key} align="right">
                            {key}
                        </Ink.NewTable.HeadCell>
                    ))}
                    <Ink.NewTable.HeadCell align="right">Commitment</Ink.NewTable.HeadCell>
                    <Ink.NewTable.HeadCell align="right">NAV</Ink.NewTable.HeadCell>
                </Ink.NewTable.Row>
            </Ink.NewTable.Head>
            <Ink.NewTable.Body>
                {sortedPartners.map(partner => (
                    <Ink.NewTable.Row key={partner.id}>
                        <Ink.NewTable.Cell>{partner.name}</Ink.NewTable.Cell>
                        {displayNavComponents.map(key => (
                            <Ink.NewTable.Cell key={key} align="right">
                                <Ink.Currency
                                    value={partner.nav_metrics.nav_components[key]}
                                    code={currency}
                                />
                            </Ink.NewTable.Cell>
                        ))}
                        <Ink.NewTable.Cell align="right">
                            <Ink.Currency
                                value={partner.metrics.end_metrics.commitment}
                                code={currency}
                            />
                        </Ink.NewTable.Cell>
                        <Ink.NewTable.Cell align="right">
                            <Ink.Currency value={partner.nav_metrics.ending_nav} code={currency} />
                        </Ink.NewTable.Cell>
                    </Ink.NewTable.Row>
                ))}
            </Ink.NewTable.Body>
            {totals && (
                <Ink.NewTable.Foot>
                    <Ink.NewTable.Row preset="totals">
                        <Ink.NewTable.Cell>Total</Ink.NewTable.Cell>
                        {displayNavComponents.map(key => (
                            <Ink.NewTable.Cell key={key} align="right">
                                <Ink.Currency
                                    value={totals.navComponents?.[key]}
                                    code={currency}
                                />
                            </Ink.NewTable.Cell>
                        ))}
                        <Ink.NewTable.Cell align="right">
                            <Ink.Currency value={totals.commitment} code={currency} />
                        </Ink.NewTable.Cell>
                        <Ink.NewTable.Cell align="right">
                            <Ink.Currency value={totals.nav} code={currency} />
                        </Ink.NewTable.Cell>
                    </Ink.NewTable.Row>
                </Ink.NewTable.Foot>
            )}
        </Ink.NewTable>
    );
};
```

**Step 4: Update `AsOfDateGpEntityNodeTile`**

Update the `totals` prop to use `navComponents` instead of `carriedInterestAccrued`:

```typescript
<PartnersTable
    isGPEntity
    partners={data.partners}
    totals={{
        commitment: data.metrics.end_metrics.commitment,
        nav: data.nav_metrics.ending_nav,
        navComponents: data.nav_metrics.nav_components,
    }}
    currency={currency}
/>
```

**Step 5: Update existing tests**

The existing `PartnersTable` tests use `render()` directly. Since the component now reads from `FundViewContext`, wrap them with `renderWithContexts` instead. Update `totals` prop to use `navComponents` instead of `carriedInterestAccrued`.

For the "GP entity" test, pass `displayNavComponents: ['Carried interest accrued']`.
For the "Partner Class" test, pass `displayNavComponents: []`.

**Step 6: Run tests**

Run: `rush test --only=@carta/entity-map -- --testPathPattern="PartnersTable" --verbose`
Expected: PASS

**Step 7: Commit**

```
refactor(entity-map): PartnersTable uses displayNavComponents from context
```

---

### Task 8: Refactor `PartnersOverTimeTable` to use `displayNavComponents`

**Files:**
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/PartnersOverTimeTable.tsx`
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/__tests__/PartnersOverTimeTable.test.tsx`

Same pattern as Task 7 but for the Journal/Events view variant. The overtime table accesses `partner.nav_metrics.end.nav_components[key]` and `totals.navMetrics.end.nav_components[key]`.

**Step 1: Write the failing test**

Add a test with `displayNavComponents: []` showing the carry column is hidden. Use `renderWithContexts`.

**Step 2: Run test to verify it fails**

Run: `rush test --only=@carta/entity-map -- --testPathPattern="PartnersOverTimeTable" --verbose`

**Step 3: Refactor the component**

Replace `isGPEntity` carry column guards with `displayNavComponents.map(...)` iteration. Keep `isGPEntity` for Member/Partner label.

**Step 4: Update existing tests to use `renderWithContexts`**

**Step 5: Run tests**

Run: `rush test --only=@carta/entity-map -- --testPathPattern="PartnersOverTimeTable" --verbose`
Expected: PASS

**Step 6: Commit**

```
refactor(entity-map): PartnersOverTimeTable uses displayNavComponents from context
```

---

### Task 9: Full test suite + lint + type check

**Step 1: Run the full test suite**

Run: `rush test --only=@carta/entity-map`
Expected: PASS

**Step 2: Type check**

Run: `rush tsc --only=@carta/entity-map`
Expected: PASS

**Step 3: Lint**

Run: `rush lint --only=@carta/entity-map`
Expected: PASS (fix any issues)

**Step 4: Commit any lint fixes**

```
style(entity-map): fix lint violations
```

---

### Task 10: Update rush changelog

**Step 1: Generate changelog entry**

Run from the entity-map project directory:

```bash
rush change --bulk --message "Render nav component metrics on node cards via displayNavComponents context" --bump-type minor
```

**Step 2: Commit**

```
chore: add rush changelog for displayNavComponents refactor
```
