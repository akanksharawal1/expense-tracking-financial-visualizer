function drawPieChart(data) {
    const ctx = document.getElementById('expensePieChart').getContext('2d');

    new Chart(ctx, {
        type: 'pie',
        data: {
            labels: data.map(item => item.category),
            datasets: [{
                data: data.map(item => item.total),
                backgroundColor: ['#ff6384', '#36a2eb', '#ffce56', '#4bc0c0', '#9966ff'],
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top',
                }
            }
        }
    });
}


function drawBarChart(income, expense) {
    const ctx = document.getElementById('monthlyBarChart').getContext('2d');

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Current Month'],
            datasets: [
                {
                    label: 'Income',
                    data: [income],
                    backgroundColor: '#36a2eb',
                },
                {
                    label: 'Expense',
                    data: [expense],
                    backgroundColor: '#ff6384',
                }
            ]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}
