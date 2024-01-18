<script lang="ts">
	import { onMount } from 'svelte';
  
	let messages: string[] = [];
	onMount(() => {
		const socket: WebSocket = new WebSocket('ws://localhost:8080/logs');
		
	
		socket.addEventListener('message', (event: MessageEvent) => {
			const logMessage = event.data;
			messages = [...messages, logMessage];

		});
	  return () => {
		socket.close();
	  };
	});
  </script>
  
  <div class="flex flex-col gap-2 p-8 md:px-24 lg:px-32">
	<h1>WebSocket Messages</h1>
	{#each messages as message (message)}
	  <p>{message}</p>
	{/each}
  </div>
  