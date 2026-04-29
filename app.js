document.addEventListener('DOMContentLoaded', () => {
    const toolsGrid = document.getElementById('toolsGrid');
    const searchInput = document.getElementById('searchInput');

    function renderTools(tools) {
        toolsGrid.innerHTML = '';
        
        if (tools.length === 0) {
            toolsGrid.innerHTML = '<p style="grid-column: 1/-1; text-align: center; padding: 50px;">검색 결과가 없습니다.</p>';
            return;
        }

        tools.forEach(tool => {
            const card = document.createElement('div');
            card.className = 'card';
            
            card.innerHTML = `
                <span class="category">${tool.category}</span>
                <h3>${tool.title}</h3>
                <p>${tool.description}</p>
                <div class="tags">
                    ${tool.tags.map(tag => `<span class="tag">#${tag}</span>`).join('')}
                </div>
                <div class="meta">
                    <span>버전: ${tool.version}</span>
                    <span>날짜: ${tool.date}</span>
                </div>
                <a href="${tool.filePath}" class="btn-download" download>다운로드 (${tool.fileName})</a>
            `;
            
            toolsGrid.appendChild(card);
        });
    }

    // 초기 렌더링
    renderTools(toolsData);

    // 검색 기능
    searchInput.addEventListener('input', (e) => {
        const searchTerm = e.target.value.toLowerCase();
        const filteredTools = toolsData.filter(tool => 
            tool.title.toLowerCase().includes(searchTerm) || 
            tool.description.toLowerCase().includes(searchTerm) ||
            tool.tags.some(tag => tag.toLowerCase().includes(searchTerm))
        );
        renderTools(filteredTools);
    });
});
