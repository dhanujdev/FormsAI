import { createFileRoute } from "@tanstack/react-router"
import { HousingGrantPage } from "@/components/HousingGrant"

export const Route = createFileRoute("/_layout/housing-grant")({
    component: HousingGrant,
    head: () => ({
        meta: [
            {
                title: "Housing Grant AI Copilot",
            },
        ],
    }),
})

function HousingGrant() {
    return <HousingGrantPage />
}
