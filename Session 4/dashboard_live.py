from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Badge, Card, CardContent, CardHeader, CardTitle,
    Checkbox, Column, H1, H2, H3, Muted, Progress, Ring, Row, Text
)
from prefab_ui.components.charts import BarChart, ChartSeries, LineChart, PieChart, Sparkline

with PrefabApp(css_class="max-w-5xl mx-auto p-6") as app:
    with Card():
        with CardHeader():
            CardTitle('Bangalore Yearly Weather Trends')
        with CardContent():
            with Column(gap=4):
                with Column(gap=1):
                    H3('Climate Overview')
                    Text("Bangalore has experienced a gradual increase in average temperatures over recent years, mirroring global climate trends. The city's weather remains a mix of comfortable, sunny days and seasonal rainfall patterns.")

                with Column(gap=2):
                    H3('Average Temperature Trend (°C)')
                    BarChart(data=[{'year': '2020', 'temp': 24.2}, {'year': '2021', 'temp': 24.5}, {'year': '2022', 'temp': 24.8}, {'year': '2023', 'temp': 25.1}, {'year': '2024', 'temp': 25.4}], series=[ChartSeries(data_key='temp', label='temp')], x_axis='year')

                with Column(gap=2):
                    H3('Historical Weather Patterns')
                    with Row(gap=3):
                        Text('Metric')
                        Text('Observation')
                    with Row(gap=3):
                        Text('Temperature Trend')
                        Text('Gradual Increase')
                    with Row(gap=3):
                        Text('General Climate')
                        Text('Tropical Savanna')
                    with Row(gap=3):
                        Text('Recent Shift')
                        Text('More variable rainfall')
                    with Row(gap=3):
                        Text('Comfort Level')
                        Text('Generally pleasant')

                with Row(gap=2):
                    Badge('Increasing Temperature', variant='warning')
                    Badge('Global Climate Influence', variant='info')
                    Badge('Vibrant City Weather', variant='success')
